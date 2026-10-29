// What every architecture scene shares, following the PRD F3.7 recipe: orthographic isometric
// camera with CameraControls, hemisphere + shadowed key + fill + baked Lightformer environment,
// three post levels, static shadows, and the browser-check probe.
import { CameraControls, Environment, Lightformer } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { EffectComposer, N8AO, SMAA, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import { useCallback, useEffect, type RefObject } from 'react'
import { Vector3 } from 'three'
import type { PostLevel } from '../bench/bench'
import type { AwsObjectPlacement } from './aws-objects'
import type { Box } from './layout'
import type { Theme } from './theme'

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

export function SceneRig({ theme, bounds, shadows, controls }: { theme: Theme; bounds: Box; shadows: boolean; controls: RefObject<CameraControls | null> }) {
  const { w, d } = bounds
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
    </>
  )
}

// Isometric framing. Not fitToBox: with an orthographic camera it snapped to the box's face
// (azimuth 90°, polar at its limit) and left zoom at 1. Zoom here fits the projected footprint.
// Returns a cleanup for the extra frames it requests.
export function frameBounds(c: CameraControls, bounds: Box, size: { width: number; height: number }, invalidate: () => void, zoom?: number | null) {
  const span = (bounds.w + bounds.d) * Math.SQRT1_2 // footprint width seen from azimuth 45°
  const fit = Math.min((size.width * 0.92) / span, (size.height * 0.92) / (span * Math.cos(POLAR)))
  void c.setTarget(bounds.x + bounds.w / 2, 0, bounds.z + bounds.d / 2, false)
  void c.rotateTo(AZIMUTH, POLAR, false)
  void c.zoomTo(zoom ?? fit, false)
  c.update(0) // apply now; otherwise the next demand-mode frame can still use the old projection
  // Demand mode: CameraControls applies the change inside a frame, so request a few more.
  const timers = [0, 50, 200, 600].map((ms) => setTimeout(invalidate, ms))
  return () => timers.forEach(clearTimeout)
}

// Shadows are static: the shadow map renders once now and again on each refresh,
// e.g. when every object has reached full size.
export function useStaticShadows() {
  const gl = useThree((s) => s.gl)
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    gl.shadowMap.autoUpdate = false
    gl.shadowMap.needsUpdate = true
  }, [gl])
  return useCallback(() => {
    gl.shadowMap.needsUpdate = true
    invalidate()
  }, [gl, invalidate])
}

// Hover/selection state and a projection helper for browser checks (scripts/check-*.mjs).
export interface SceneProbe {
  hovered: string | null
  selected: string | null
  screenPoint: (id: string) => { x: number; y: number } | null
}

const NO_EXTRA = {}

// `extra` adds scene-specific fields; pass a stable object.
export function useSceneProbe(placements: readonly AwsObjectPlacement[], hovered: string | null, selected: string | null, extra: object = NO_EXTRA) {
  const camera = useThree((s) => s.camera)
  const gl = useThree((s) => s.gl)
  useEffect(() => {
    const byId = new Map(placements.map((p) => [p.id, p]))
    const probe: SceneProbe = {
      ...extra,
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
  }, [hovered, selected, placements, camera, gl, extra])
}
