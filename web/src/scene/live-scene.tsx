// Live scene: draws whatever resource graph the lab-server last sent.
// The camera frames the scene once, when the first non-empty graph arrives, and again on request
// (fitKey changes); later graph updates keep the view the learner chose.
// With a builder attached, it also follows palette drags and edge drags (PRD F4.2, F4.6); what
// the learner builds appears only when a later graph contains it (F4.5).
import { CameraControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Vector3 } from 'three'
import type { Vec3 } from '../builder/drop-targets'
import { resourceId, type SceneGraph } from '../graph/graph-to-scene'
import type { ApiEvent } from '../graph/types'
import { ApiFlyLayer } from './api-fly-layer'
import { AwsObjectLayer, type ThemeName } from './aws-objects'
import { ConnectHandle, ConnectLine, HANDLE_RISE } from './connect-line'
import { DropHighlight } from './drop-highlight'
import { EdgeLayer } from './edge-layer'
import { LabelLayer } from './label-layer'
import { computeLayout, TRAY_H, type LaidOutGroup } from './layout'
import { edgeAnchors, scenePlacements } from './object-placements'
import { PointerProbe, type ScenePointer } from './pointer-probe'
import { frameBounds, PostFx, SceneRig, useSceneProbe, useStaticShadows } from './scene-rig'
import { THEMES } from './theme'
import { TrayLayer } from './tray-layer'

export interface BuilderPointer extends ScenePointer {
  object: string | null // resource id of the object under the pointer
}

// What the builder needs from the scene, and tells it to show.
export interface SceneBuilder {
  mode: 'drag' | 'connect' | null
  accepts: (tray: LaidOutGroup) => boolean // trays to tint during a drag or connection
  target: string | null // valid target under the pointer
  connectFrom: string | null
  handleFor: string | null // the selected object, when an edge can start from it
  onConnectStart: (id: string) => void
  onPointer: (p: BuilderPointer, end: boolean) => void
}

export interface LiveSceneProps {
  scene: SceneGraph
  events: readonly ApiEvent[]
  theme: ThemeName
  fitKey: number
  selected: string | null
  onSelect: (id: string | null) => void
  builder?: SceneBuilder
}

export function LiveScene({ scene, events, theme: themeName, fitKey, selected, onSelect, builder }: LiveSceneProps) {
  const theme = THEMES[themeName]
  const layout = useMemo(() => computeLayout(scene), [scene])
  const placements = useMemo(() => scenePlacements(scene, layout), [scene, layout])
  const anchors = useMemo(() => edgeAnchors(placements), [placements])
  const [hovered, setHovered] = useState<string | null>(null)
  // Read by the pointer probe in the same event, before the state update lands.
  const hoveredRef = useRef<string | null>(null)
  const onHover = useCallback((id: string | null) => {
    hoveredRef.current = id
    setHovered(id)
  }, [])
  const controls = useRef<CameraControls>(null)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)
  const camera = useThree((s) => s.camera)
  const gl = useThree((s) => s.gl)

  // Builder gestures. The camera stays still while an edge is drawn, and from the moment the
  // pointer is over the handle, so pressing it does not start an orbit.
  const mode = builder?.mode ?? null
  const builderRef = useRef(builder)
  builderRef.current = builder
  const [overHandle, setOverHandle] = useState(false)
  const [linePoint, setLinePoint] = useState<Vec3 | null>(null)
  const handleAt = builder?.handleFor && mode === null ? anchors.get(builder.handleFor)?.at : undefined
  const lineFrom = mode === 'connect' && builder?.connectFrom ? anchors.get(builder.connectFrom)?.at : undefined
  useEffect(() => setOverHandle(false), [handleAt])
  useEffect(() => {
    if (controls.current) controls.current.enabled = mode === null && !overHandle
    gl.domElement.style.cursor = overHandle || mode === 'connect' ? 'crosshair' : ''
  }, [mode, overHandle, gl])
  useEffect(() => {
    if (mode !== 'connect') setLinePoint(null)
  }, [mode])
  const report = useCallback((p: ScenePointer, end: boolean) => {
    if (builderRef.current?.mode === 'connect') setLinePoint(p.point)
    builderRef.current?.onPointer({ ...p, object: hoveredRef.current && resourceId(hoveredRef.current) }, end)
  }, [])
  const onMove = useCallback((p: ScenePointer) => report(p, false), [report])
  const onEnd = useCallback((p: ScenePointer) => report(p, true), [report])

  // Frame on the first graph with more than the region tray, and whenever fitKey changes.
  const framed = useRef<{ key: number; content: boolean } | null>(null)
  const hasContent = scene.nodes.length > 1
  useEffect(() => {
    const prev = framed.current
    if (!controls.current || (prev && prev.key === fitKey && (prev.content || !hasContent))) return
    framed.current = { key: fitKey, content: hasContent }
    return frameBounds(controls.current, layout.bounds, size, invalidate)
  }, [fitKey, hasContent, layout.bounds, size, invalidate])

  const refreshShadows = useStaticShadows()
  // Browser checks read an object's animated scale, the number of API particles in the air and
  // the frames rendered so far (idle must stay at zero).
  const scaleRef = useRef<((id: string) => number | null) | null>(null)
  const flying = useRef(0)
  const frames = useRef(0)
  useFrame(() => void frames.current++)
  // Builder checks also need the screen point of a tray's centre and of the connect handle.
  const view = useRef({ groups: layout.groups, handleAt, camera, gl })
  view.current = { groups: layout.groups, handleAt, camera, gl }
  const probeExtra = useMemo(() => {
    const toScreen = (x: number, y: number, z: number) => {
      const { camera, gl } = view.current
      const v = new Vector3(x, y, z).project(camera)
      const rect = gl.domElement.getBoundingClientRect()
      return { x: rect.left + ((v.x + 1) / 2) * rect.width, y: rect.top + ((1 - v.y) / 2) * rect.height }
    }
    return {
      scaleOf: (id: string) => scaleRef.current?.(id) ?? null,
      flying: () => flying.current,
      frames: () => frames.current,
      trayPoint: (id: string) => {
        const g = view.current.groups.find((t) => t.node.id === id)
        return g ? toScreen(g.x + g.w / 2, g.y + TRAY_H, g.z + g.d / 2) : null
      },
      // A point on the tray that no tray inside it covers, near its centre: where a drop lands
      // on this tray itself rather than on a child.
      freePoint: (id: string) => {
        const { groups } = view.current
        const g = groups.find((t) => t.node.id === id)
        if (!g) return null
        const inner = groups.filter((t) => t.level > g.level)
        const steps = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.12, 0.88, 0.06, 0.94]
        for (const fx of steps)
          for (const fz of steps) {
            const x = g.x + fx * g.w
            const z = g.z + fz * g.d
            const covered = inner.some((t) => x > t.x - 0.2 && x < t.x + t.w + 0.2 && z > t.z - 0.2 && z < t.z + t.d + 0.2)
            if (!covered) return toScreen(x, g.y + TRAY_H, z)
          }
        return null
      },
      handlePoint: () => {
        const at = view.current.handleAt
        return at ? toScreen(at[0], at[1] + HANDLE_RISE, at[2]) : null
      },
    }
  }, [])
  useSceneProbe(placements, hovered, selected, probeExtra)

  return (
    <>
      <SceneRig theme={theme} bounds={layout.bounds} shadows controls={controls} />
      <TrayLayer groups={layout.groups} theme={theme} />
      <AwsObjectLayer
        placements={placements}
        theme={themeName}
        hovered={hovered}
        selected={selected}
        outlineColor={theme.outline}
        onHover={onHover}
        onSelect={onSelect}
        onSettled={refreshShadows}
        scaleRef={scaleRef}
      />
      <LabelLayer leaves={layout.leaves} theme={theme} />
      <EdgeLayer edges={scene.edges} anchors={anchors} theme={theme} />
      <ApiFlyLayer events={events} scene={scene} anchors={anchors} theme={theme} countRef={flying} />
      {builder && mode !== null && (
        <>
          <PointerProbe groups={layout.groups} onMove={onMove} onEnd={onEnd} />
          <DropHighlight groups={layout.groups} accepts={builder.accepts} target={builder.target} theme={theme} />
        </>
      )}
      {builder && handleAt && (
        <ConnectHandle at={handleAt} theme={theme} onHover={setOverHandle} onStart={() => builder.onConnectStart(builder.handleFor!)} />
      )}
      {lineFrom && linePoint && <ConnectLine from={lineFrom} to={linePoint} valid={builder?.target != null} theme={theme} />}
      <PostFx level="full" />
    </>
  )
}
