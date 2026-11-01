// Every registry kind on one board, plus a kind this build does not know (drawn as the fallback
// object with its yellow outline), for checking the object library by eye in both themes.
// URL: ?view=gallery&theme=light|dark&coverage=0.75&zoom=<n>&post=full|lite|flat
// Sets window.__galleryReady once the frame is static, so scripts/check-scene.mjs can screenshot it.
import { CameraControls, Environment, Lightformer, Line, Text } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import type { PostLevel } from '../bench/bench'
import { AZIMUTH, POLAR, PostFx } from '../scene/scene-rig'
import { kindView, registryData } from '../registry/registry'
import type { AwsObjectPlacement, ThemeName } from '../scene/aws-objects'
import { attachPosition, AwsObjectLayer } from '../scene/aws-objects'
import { THEMES } from '../scene/theme'
import { FONT } from '../scene/tray-layer'

const COL = 5.2 // wide enough for the longest caption (Transit Gateway Attachment)
const ROW = 3.6
const PER_ROW = 8 // the registry has dozens of kinds: wrap them into a grid that fits the canvas
const ROLE_ROWS = ['block', 'tray-badge', 'attach-badge'] as const
// Not in any registry: shows what an unsupported kind from the server looks like.
export const GALLERY_UNKNOWN_KIND = 'gallery-unknown-kind'

interface Cell {
  id: string
  kind: string
  x: number
  z: number
  caption: string
}

// Each role starts a new row; the last row seats the attach badges on a host, to show them in context.
export function boardCells(): { cells: Cell[]; rows: number } {
  const grid: Omit<Cell, 'x' | 'z'>[][] = []
  for (const role of ROLE_ROWS) {
    const views = registryData().kinds.map((k) => kindView(k.kind))
    if (role === 'block') views.push(kindView(GALLERY_UNKNOWN_KIND))
    const kinds = views.filter((e) => e.role === role || (role === 'tray-badge' && e.role === 'outline-only'))
    for (let i = 0; i < kinds.length; i += PER_ROW)
      grid.push(kinds.slice(i, i + PER_ROW).map((e) => ({ id: `solo-${e.kind}`, kind: e.kind, caption: e.fallback ? 'Loại lạ (dự phòng)' : e.label })))
  }
  grid.push([
    { id: 'host-instance', kind: 'instance', caption: 'EC2 + SG + EIP' },
    { id: 'host-nat', kind: 'nat', caption: 'NAT + EIP' },
  ])
  const cells = grid.flatMap((row, r) =>
    row.map((c, i) => ({ ...c, x: (i - (PER_ROW - 1) / 2) * COL, z: (r - (grid.length - 1) / 2) * ROW })),
  )
  return { cells, rows: grid.length }
}

export interface GalleryConfig {
  theme: ThemeName
  coverage: number
  post: PostLevel
  zoom: number | null
}

export function AwsObjectsGallery({ cfg }: { cfg: GalleryConfig }) {
  const theme = THEMES[cfg.theme]
  const { cells, rows } = useMemo(boardCells, [])
  const controls = useRef<CameraControls>(null)
  const gl = useThree((s) => s.gl)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)

  // Each object on its own, plus the attach badges seated on a host block to show them in context.
  const placements = useMemo(() => {
    const out: AwsObjectPlacement[] = []
    for (const c of cells) {
      if (kindView(c.kind).role === 'outline-only') continue
      out.push({ id: c.id, kind: c.kind, position: [c.x, 0, c.z] })
    }
    const hostInstance = out.find((p) => p.id === 'host-instance')!
    const hostNat = out.find((p) => p.id === 'host-nat')!
    out.push({ id: 'ctx-sg', kind: 'security-group', position: attachPosition(hostInstance, 0) })
    out.push({ id: 'ctx-eip-instance', kind: 'elastic-ip', position: attachPosition(hostInstance, 1) })
    out.push({ id: 'ctx-eip-nat', kind: 'elastic-ip', position: attachPosition(hostNat, 0) })
    return out
  }, [cells])

  const width = PER_ROW * COL
  const depth = rows * ROW
  useLayoutEffect(() => {
    const c = controls.current
    if (!c) return
    // The board seen from the scene's azimuth: its diagonal across, its foreshortened diagonal up.
    const diagonal = Math.hypot(width, depth)
    const fit = Math.min((size.width * 0.92) / diagonal, (size.height * 0.92) / (diagonal * Math.cos(POLAR) + 1.5))
    void c.setTarget(0, 0, 0, false)
    void c.rotateTo(AZIMUTH, POLAR, false)
    void c.zoomTo(cfg.zoom ?? fit, false)
    c.update(0)
    const timers = [0, 50, 200, 600].map((ms) => setTimeout(invalidate, ms))
    return () => timers.forEach(clearTimeout)
  }, [cfg.zoom, invalidate, size.width, size.height, width, depth])

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
        shadow-camera-left={-26}
        shadow-camera-right={26}
        shadow-camera-top={26}
        shadow-camera-bottom={-26}
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

      <mesh position={[0, -0.08, 0]} receiveShadow userData={{ treatAsOpaque: true }}>
        <boxGeometry args={[width + COL / 2, 0.16, depth]} />
        <meshStandardMaterial color={ground.fill} roughness={0.9} metalness={0} />
      </mesh>

      <AwsObjectLayer placements={placements} theme={cfg.theme} coverage={cfg.coverage} animate={false} />

      {cells.map((c) =>
        kindView(c.kind).role === 'outline-only' ? (
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
      {cells.map((c) => (
        <Text
          key={`caption-${c.id}`}
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
          {kindView(c.kind).role === 'outline-only' ? "AZ (chỉ viền)" : c.caption}
        </Text>
      ))}
      <PostFx level={cfg.post} />
    </>
  )
}
