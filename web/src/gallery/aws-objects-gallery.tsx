// Every manifest kind on one board, for checking the object library by eye in both themes.
// URL: ?view=gallery&theme=light|dark&coverage=0.75&zoom=<n>&post=full|lite|flat
// Sets window.__galleryReady once the frame is static, so scripts/check-scene.mjs can screenshot it.
import { CameraControls, Environment, Lightformer, Line, Text } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import type { PostLevel } from '../bench/bench'
import { AZIMUTH, POLAR, PostFx } from '../scene/scene-rig'
import type { AwsKind, AwsObjectPlacement, ThemeName } from '../scene/aws-objects'
import { attachPosition, AwsObjectLayer, MANIFEST, MANIFEST_BY_KIND } from '../scene/aws-objects'
import { THEMES } from '../scene/theme'
import { FONT } from '../scene/tray-layer'

const COL = 3.8
const ROW = 3.6
const ROLE_ROWS = ['block', 'tray-badge', 'attach-badge'] as const

interface Cell {
  kind: AwsKind
  x: number
  z: number
  caption: string
}

function boardCells(): Cell[] {
  const cells: Cell[] = []
  ROLE_ROWS.forEach((role, r) => {
    const kinds = MANIFEST.filter((e) => e.role === role || (role === 'tray-badge' && e.role === 'outline-only'))
    kinds.forEach((e, c) => cells.push({ kind: e.kind, x: (c - (kinds.length - 1) / 2) * COL, z: (r - 1) * ROW, caption: e.label }))
  })
  return cells
}

export interface GalleryConfig {
  theme: ThemeName
  coverage: number
  post: PostLevel
  zoom: number | null
}

export function AwsObjectsGallery({ cfg }: { cfg: GalleryConfig }) {
  const theme = THEMES[cfg.theme]
  const cells = useMemo(boardCells, [])
  const controls = useRef<CameraControls>(null)
  const gl = useThree((s) => s.gl)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)

  // Each object on its own, plus the attach badges seated on a host block to show them in context.
  const placements = useMemo(() => {
    const out: AwsObjectPlacement[] = []
    for (const c of cells) {
      if (MANIFEST_BY_KIND[c.kind].role === 'outline-only') continue
      out.push({ id: `solo-${c.kind}`, kind: c.kind, position: [c.x, 0, c.z] })
    }
    const lastRow = ROW
    const hostInstance: AwsObjectPlacement = { id: 'host-instance', kind: 'instance', position: [2 * COL, 0, lastRow] }
    const hostNat: AwsObjectPlacement = { id: 'host-nat', kind: 'nat', position: [3 * COL, 0, lastRow] }
    out.push(hostInstance, hostNat)
    out.push({ id: 'ctx-sg', kind: 'security-group', position: attachPosition(hostInstance, 0) })
    out.push({ id: 'ctx-eip-instance', kind: 'elastic-ip', position: attachPosition(hostInstance, 1) })
    out.push({ id: 'ctx-eip-nat', kind: 'elastic-ip', position: attachPosition(hostNat, 0) })
    return out
  }, [cells])

  useLayoutEffect(() => {
    const c = controls.current
    if (!c) return
    const span = 7 * COL
    const fit = Math.min((size.width * 0.9) / span, (size.height * 0.9) / (span * Math.cos(POLAR) + 3 * ROW))
    void c.setTarget(0.6 * COL, 0, 0, false)
    void c.rotateTo(AZIMUTH, POLAR, false)
    void c.zoomTo(cfg.zoom ?? fit, false)
    c.update(0)
    const timers = [0, 50, 200, 600].map((ms) => setTimeout(invalidate, ms))
    return () => timers.forEach(clearTimeout)
  }, [cfg.zoom, invalidate, size.width, size.height])

  useEffect(() => {
    const w = window as unknown as { __galleryReady?: boolean }
    w.__galleryReady = false
    gl.shadowMap.autoUpdate = false
    gl.shadowMap.needsUpdate = true
    let ready: ReturnType<typeof setTimeout> | undefined
    const t = setTimeout(() => {
      gl.shadowMap.needsUpdate = true
      invalidate()
      ready = setTimeout(() => (w.__galleryReady = true), 400)
    }, 800)
    return () => {
      clearTimeout(t)
      clearTimeout(ready)
    }
  }, [gl, invalidate, cfg.theme, cfg.coverage])

  const ground = theme.groups.region
  return (
    <>
      <color attach="background" args={[theme.background]} />
      <CameraControls ref={controls} makeDefault minPolarAngle={(15 * Math.PI) / 180} maxPolarAngle={(80 * Math.PI) / 180} />
      <hemisphereLight args={[theme.hemisphere.sky, theme.hemisphere.ground, theme.hemisphere.intensity]} />
      <directionalLight
        position={[8, 60, 12]}
        intensity={theme.key}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
        shadow-camera-near={1}
        shadow-camera-far={200}
        shadow-bias={-0.0004}
      />
      <directionalLight position={[-10, 30, -8]} intensity={theme.fill} />
      <Environment frames={1} resolution={256} environmentIntensity={theme.environment}>
        <Lightformer form="rect" intensity={2} position={[0, 10, 0]} rotation-x={Math.PI / 2} scale={[20, 20, 1]} />
        <Lightformer form="rect" intensity={1} position={[-10, 4, 6]} rotation-y={Math.PI / 3} scale={[10, 4, 1]} />
        <Lightformer form="ring" intensity={0.6} position={[8, 3, -8]} scale={4} />
      </Environment>

      <mesh position={[0.6 * COL, -0.08, 0]} receiveShadow userData={{ treatAsOpaque: true }}>
        <boxGeometry args={[8 * COL, 0.16, 4 * ROW]} />
        <meshStandardMaterial color={ground.fill} roughness={0.9} metalness={0} />
      </mesh>

      <AwsObjectLayer placements={placements} theme={cfg.theme} coverage={cfg.coverage} animate={false} />

      {cells.map((c) =>
        MANIFEST_BY_KIND[c.kind].role === 'outline-only' ? (
          <Line
            key={`outline-${c.kind}`}
            points={[[c.x - 0.7, 0.01, c.z - 0.7], [c.x + 0.7, 0.01, c.z - 0.7], [c.x + 0.7, 0.01, c.z + 0.7], [c.x - 0.7, 0.01, c.z + 0.7], [c.x - 0.7, 0.01, c.z - 0.7]]}
            color={theme.groups.az.border}
            lineWidth={1.8}
            dashed
            dashSize={0.3}
            gapSize={0.2}
          />
        ) : null,
      )}
      {[...cells, { kind: 'instance' as AwsKind, x: 2 * COL, z: ROW, caption: 'EC2 + SG + EIP' }, { kind: 'nat' as AwsKind, x: 3 * COL, z: ROW, caption: 'NAT + EIP' }].map((c) => (
        <Text
          key={`caption-${c.caption}`}
          font={FONT}
          fontSize={0.32}
          color={theme.label}
          outlineWidth={0.02}
          outlineColor={theme.labelOutline}
          anchorX="center"
          anchorY="top"
          rotation={[-Math.PI / 2, 0, 0]}
          position={[c.x, 0.01, c.z + 1.0]}
        >
          {MANIFEST_BY_KIND[c.kind].role === 'outline-only' ? "AZ (chỉ viền)" : c.caption}
        </Text>
      ))}
      <PostFx level={cfg.post} />
    </>
  )
}
