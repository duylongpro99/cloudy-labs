// Scene root following the PRD F3.7 recipe: orthographic isometric camera with CameraControls,
// hemisphere + shadowed key + fill + baked Lightformer environment, and three post levels.
// Resources are drawn by the AWS object library; trays, edges and labels stay scene layers.
import { CameraControls, Environment, Lightformer } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { EffectComposer, N8AO, SMAA, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Vector3 } from 'three'
import type { BenchConfig, BenchResult, PostLevel } from '../bench/bench'
import { BenchRunner } from '../bench/bench-runner'
import { AwsObjectLayer } from './aws-objects'
import { EdgeLayer } from './edge-layer'
import { buildFixture } from './fixture'
import { LabelLayer } from './label-layer'
import { computeLayout } from './layout'
import { scenePlacements } from './object-placements'
import { THEMES } from './theme'
import { TrayLayer } from './tray-layer'

export const AZIMUTH = Math.PI / 4 // 45°
export const POLAR = Math.PI / 2 - (35 * Math.PI) / 180 // 35° elevation

export function PostFx({ level }: { level: PostLevel }) {
  if (level === 'flat') return null
  return (
    <EffectComposer multisampling={0}>
      {level === 'full' ? <N8AO halfRes quality="medium" aoRadius={2} distanceFalloff={1} intensity={2.5} /> : <></>}
      <SMAA />
      <ToneMapping mode={ToneMappingMode.NEUTRAL} />
    </EffectComposer>
  )
}

// Hover/selection state and a projection helper for browser checks (scripts/check-scene.mjs).
interface SceneProbe {
  hovered: string | null
  selected: string | null
  screenPoint: (id: string) => { x: number; y: number } | null
}

export function ArchitectureScene({ cfg, onDone }: { cfg: BenchConfig; onDone: (r: BenchResult) => void }) {
  const theme = THEMES[cfg.theme]
  const fixture = useMemo(() => buildFixture(42), [])
  const layout = useMemo(() => computeLayout(fixture), [fixture])
  const placements = useMemo(() => scenePlacements(fixture, layout), [fixture, layout])
  const [hovered, setHovered] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(cfg.mode === 'view' ? null : 'i-000')
  const controls = useRef<CameraControls>(null)
  const gl = useThree((s) => s.gl)
  const camera = useThree((s) => s.camera)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)
  const shadows = cfg.post !== 'flat'

  // Isometric framing. Not fitToBox: with an orthographic camera it snapped to the box's face
  // (azimuth 90°, polar at its limit) and left zoom at 1. Zoom here fits the projected footprint.
  useLayoutEffect(() => {
    const c = controls.current
    if (!c) return
    const { w, d } = layout.bounds
    const span = (w + d) * Math.SQRT1_2 // footprint width seen from azimuth 45°
    const fit = Math.min((size.width * 0.92) / span, (size.height * 0.92) / (span * Math.cos(POLAR)))
    void c.setTarget(0, 0, 0, false)
    void c.rotateTo(AZIMUTH, POLAR, false)
    void c.zoomTo(cfg.zoom ?? fit, false)
    c.update(0) // apply now; otherwise the next demand-mode frame can still use the old projection
    // Demand mode: CameraControls applies the change inside a frame, so request a few more.
    const timers = [0, 50, 200, 600].map((ms) => setTimeout(invalidate, ms))
    return () => timers.forEach(clearTimeout)
  }, [cfg.zoom, invalidate, layout.bounds, size.width, size.height])

  // Shadows are static: render the shadow map once now and again when every object has reached full size.
  useEffect(() => {
    gl.shadowMap.autoUpdate = false
    gl.shadowMap.needsUpdate = true
  }, [gl])
  const refreshShadows = useCallback(() => {
    gl.shadowMap.needsUpdate = true
    invalidate()
  }, [gl, invalidate])

  useEffect(() => {
    const byId = new Map(placements.map((p) => [p.id, p]))
    const probe: SceneProbe = {
      hovered,
      selected,
      screenPoint: (id) => {
        const p = byId.get(id)
        if (!p) return null
        const v = new Vector3(...p.position).project(camera)
        const rect = gl.domElement.getBoundingClientRect()
        return { x: rect.left + ((v.x + 1) / 2) * rect.width, y: rect.top + ((1 - v.y) / 2) * rect.height }
      },
    }
    ;(window as unknown as { __scene: SceneProbe }).__scene = probe
  }, [hovered, selected, placements, camera, gl])

  const { w, d } = layout.bounds
  const half = Math.max(w, d) / 2 + 4
  return (
    <>
      <color attach="background" args={[theme.background]} />
      <CameraControls ref={controls} makeDefault minPolarAngle={(15 * Math.PI) / 180} maxPolarAngle={(80 * Math.PI) / 180} />

      <hemisphereLight args={[theme.hemisphere.sky, theme.hemisphere.ground, theme.hemisphere.intensity]} />
      <directionalLight
        position={[w * 0.35, 60, d * 0.55]}
        intensity={theme.key}
        castShadow={shadows}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-half}
        shadow-camera-right={half}
        shadow-camera-top={half}
        shadow-camera-bottom={-half}
        shadow-camera-near={1}
        shadow-camera-far={200}
        shadow-bias={-0.0004}
      />
      <directionalLight position={[-w * 0.4, 30, -d * 0.3]} intensity={theme.fill} />
      <Environment frames={1} resolution={256} environmentIntensity={theme.environment}>
        <Lightformer form="rect" intensity={2} position={[0, 10, 0]} rotation-x={Math.PI / 2} scale={[20, 20, 1]} />
        <Lightformer form="rect" intensity={1} position={[-10, 4, 6]} rotation-y={Math.PI / 3} scale={[10, 4, 1]} />
        <Lightformer form="ring" intensity={0.6} position={[8, 3, -8]} scale={4} />
      </Environment>

      <TrayLayer groups={layout.groups} theme={theme} />
      <AwsObjectLayer
        placements={placements}
        theme={cfg.theme}
        shadows={shadows}
        hovered={hovered}
        selected={selected}
        outlineColor={theme.outline}
        onHover={setHovered}
        onSelect={setSelected}
        onSettled={refreshShadows}
      />
      <LabelLayer leaves={layout.leaves} theme={theme} />
      <EdgeLayer edges={fixture.edges} leaves={layout.leaves} theme={theme} />
      <PostFx level={cfg.post} />
      {cfg.mode !== 'view' && <BenchRunner cfg={cfg} controls={controls} onDone={onDone} />}
    </>
  )
}
