// Scene root following the PRD F3.7 recipe: orthographic isometric camera with CameraControls,
// hemisphere + shadowed key + fill + baked Lightformer environment, and three post levels.
import { CameraControls, Environment, Lightformer } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { EffectComposer, N8AO, SMAA, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { BenchConfig, BenchResult, PostLevel } from '../bench'
import { buildFixture } from '../fixture'
import { BenchRunner } from './bench-runner'
import { EdgeLayer } from './edge-layer'
import { computeLayout } from './layout'
import { NodeLayer } from './node-layer'
import { THEMES } from './theme'
import { TrayLayer } from './tray-layer'

const AZIMUTH = Math.PI / 4 // 45°
const POLAR = Math.PI / 2 - (35 * Math.PI) / 180 // 35° elevation

function PostFx({ level }: { level: PostLevel }) {
  if (level === 'flat') return null
  return (
    <EffectComposer multisampling={0}>
      {level === 'full' ? <N8AO halfRes quality="medium" aoRadius={2} distanceFalloff={1} intensity={2.5} /> : <></>}
      <SMAA />
      <ToneMapping mode={ToneMappingMode.NEUTRAL} />
    </EffectComposer>
  )
}

export function ArchitectureScene({ cfg, onDone }: { cfg: BenchConfig; onDone: (r: BenchResult) => void }) {
  const theme = THEMES[cfg.theme]
  const fixture = useMemo(() => buildFixture(42), [])
  const layout = useMemo(() => computeLayout(fixture), [fixture])
  const [selected, setSelected] = useState<string | null>(cfg.mode === 'view' ? null : 'i-000')
  const controls = useRef<CameraControls>(null)
  const gl = useThree((s) => s.gl)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)
  const shadows = cfg.post !== 'flat'

  // Isometric framing. Not fitToBox: with an orthographic camera it snapped to the box's face
  // (azimuth 90°, polar at its limit) and left zoom at 1. Zoom here fits the projected footprint.
  useLayoutEffect(() => {
    const c = controls.current
    if (!c) return
    ;(window as unknown as { __controls: CameraControls }).__controls = c // spike debugging hook
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

  // Shadows are static: re-render the shadow map only once the entrance animation has settled.
  useEffect(() => {
    gl.shadowMap.autoUpdate = false
    gl.shadowMap.needsUpdate = true
    const t = setTimeout(() => {
      gl.shadowMap.needsUpdate = true
      invalidate()
    }, 1800)
    return () => clearTimeout(t)
  }, [gl, invalidate])

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
      <NodeLayer leaves={layout.leaves} theme={theme} themeName={cfg.theme} selected={selected} onSelect={setSelected} />
      <EdgeLayer edges={fixture.edges} leaves={layout.leaves} theme={theme} />
      <PostFx level={cfg.post} />
      {cfg.mode !== 'view' && <BenchRunner cfg={cfg} controls={controls} onDone={onDone} />}
    </>
  )
}
