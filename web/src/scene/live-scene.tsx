// Live scene: draws whatever resource graph the lab-server last sent.
// The camera frames the scene once, when the first non-empty graph arrives, and again on request
// (fitKey changes); later graph updates keep the view the learner chose.
import { CameraControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { SceneGraph } from '../graph/graph-to-scene'
import type { ApiEvent } from '../graph/types'
import { ApiFlyLayer } from './api-fly-layer'
import { AwsObjectLayer, type ThemeName } from './aws-objects'
import { EdgeLayer } from './edge-layer'
import { LabelLayer } from './label-layer'
import { computeLayout } from './layout'
import { edgeAnchors, scenePlacements } from './object-placements'
import { frameBounds, PostFx, SceneRig, useSceneProbe, useStaticShadows } from './scene-rig'
import { THEMES } from './theme'
import { TrayLayer } from './tray-layer'

export interface LiveSceneProps {
  scene: SceneGraph
  events: readonly ApiEvent[]
  theme: ThemeName
  fitKey: number
  selected: string | null
  onSelect: (id: string | null) => void
}

export function LiveScene({ scene, events, theme: themeName, fitKey, selected, onSelect }: LiveSceneProps) {
  const theme = THEMES[themeName]
  const layout = useMemo(() => computeLayout(scene), [scene])
  const placements = useMemo(() => scenePlacements(scene, layout), [scene, layout])
  const anchors = useMemo(() => edgeAnchors(placements), [placements])
  const [hovered, setHovered] = useState<string | null>(null)
  const controls = useRef<CameraControls>(null)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)

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
  const probeExtra = useMemo(
    () => ({ scaleOf: (id: string) => scaleRef.current?.(id) ?? null, flying: () => flying.current, frames: () => frames.current }),
    [],
  )
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
        onHover={setHovered}
        onSelect={onSelect}
        onSettled={refreshShadows}
        scaleRef={scaleRef}
      />
      <LabelLayer leaves={layout.leaves} theme={theme} />
      <EdgeLayer edges={scene.edges} anchors={anchors} theme={theme} />
      <ApiFlyLayer events={events} scene={scene} anchors={anchors} theme={theme} countRef={flying} />
      <PostFx level="full" />
    </>
  )
}
