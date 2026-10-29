// Configuration edges as raised Bezier curves (one merged draw call per edge style),
// plus instanced pulse particles travelling along them.
// Styles: route is solid and coloured by its target (internet gateway or NAT) with its CIDR as a label,
// association is a thin dash, uses-key is dotted; edges without a kind keep the plain benchmark style.
import { Billboard, Line, Text } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { memo, useMemo, useRef } from 'react'
import { type Group, InstancedMesh, Object3D, QuadraticBezierCurve3, Vector3 } from 'three'
import type { FixtureEdge } from './fixture'
import { LABEL_MIN_ZOOM } from './label-layer'
import type { EdgeAnchor } from './object-placements'
import type { Theme } from './theme'
import { FONT } from './tray-layer'

const SEGMENTS = 20
const PULSE_SPEED = 0.35 // curve lengths per second

interface EdgeStyle {
  color: string
  width: number
  dash?: { dashSize: number; gapSize: number }
}

function edgeStyle(e: FixtureEdge, target: EdgeAnchor, theme: Theme): EdgeStyle {
  const c = theme.edges
  switch (e.kind) {
    case 'route':
      return { color: target.kind === 'igw' ? c.routeIgw : target.kind === 'nat' ? c.routeNat : theme.edge, width: 2.2 }
    case 'association':
      return { color: c.association, width: 1, dash: { dashSize: 0.35, gapSize: 0.25 } }
    case 'uses-key':
      return { color: c.usesKey, width: 1.4, dash: { dashSize: 0.08, gapSize: 0.2 } }
    default:
      return { color: theme.edge, width: 1.6 }
  }
}

// `anchors` comes from edgeAnchors(); an edge whose end has no object is skipped.
export const EdgeLayer = memo(function EdgeLayer({ edges, anchors, theme }: { edges: FixtureEdge[]; anchors: Map<string, EdgeAnchor>; theme: Theme }) {
  const curves = useMemo(() => {
    return edges.flatMap((e) => {
      const a = anchors.get(e.from)
      const b = anchors.get(e.to)
      if (!a || !b) return []
      const start = new Vector3(...a.at)
      const end = new Vector3(...b.at)
      const mid = start.clone().add(end).multiplyScalar(0.5)
      mid.y += 1 + start.distanceTo(end) * 0.18
      return [{ edge: e, curve: new QuadraticBezierCurve3(start, mid, end), style: edgeStyle(e, b, theme) }]
    })
  }, [edges, anchors, theme])

  // One LineSegments2 per distinct style: every curve becomes SEGMENTS short segment pairs.
  const batches = useMemo(() => {
    const out = new Map<string, { style: EdgeStyle; points: Vector3[] }>()
    for (const { curve, style } of curves) {
      const key = JSON.stringify(style)
      const batch = out.get(key) ?? out.set(key, { style, points: [] }).get(key)!
      const pts = curve.getPoints(SEGMENTS)
      for (let i = 0; i < pts.length - 1; i++) batch.points.push(pts[i], pts[i + 1])
    }
    return [...out]
  }, [curves])

  const labels = useMemo(
    () => curves.filter((c) => c.edge.kind === 'route' && c.edge.label).map((c) => ({ id: `${c.edge.from}>${c.edge.to}:${c.edge.label}`, text: c.edge.label!, at: c.curve.getPoint(0.5) })),
    [curves],
  )

  const pulses = useRef<InstancedMesh>(null)
  const labelGroup = useRef<Group>(null)
  const dummy = useMemo(() => new Object3D(), [])
  const tmp = useMemo(() => new Vector3(), [])
  // Demand mode: pulses move only on frames something else requested (orbit, hover, animation).
  // Requesting frames here would break the zero-idle-frame budget, so they hold still at rest.
  useFrame(({ clock, camera }) => {
    if (labelGroup.current) labelGroup.current.visible = camera.zoom >= LABEL_MIN_ZOOM
    const mesh = pulses.current
    if (!mesh) return
    const t = clock.getElapsedTime() * PULSE_SPEED
    curves.forEach(({ curve }, i) => {
      curve.getPoint((t + i * 0.137) % 1, tmp)
      dummy.position.copy(tmp)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <group>
      {batches.map(([key, { style, points }]) => (
        <Line
          key={key}
          points={points}
          segments
          color={style.color}
          lineWidth={style.width}
          dashed={!!style.dash}
          {...style.dash}
          transparent
          opacity={0.85}
        />
      ))}
      {/* Remount when the count changes: an InstancedMesh's capacity is fixed at creation. */}
      <instancedMesh key={curves.length} ref={pulses} args={[undefined, undefined, curves.length]} frustumCulled={false}>
        <sphereGeometry args={[0.14, 12, 8]} />
        <meshBasicMaterial color={theme.pulse} toneMapped={false} />
      </instancedMesh>
      <group ref={labelGroup}>
        {labels.map((l) => (
          <Billboard key={l.id} position={[l.at.x, l.at.y + 0.2, l.at.z]}>
            <Text font={FONT} fontSize={0.3} color={theme.label} outlineWidth={0.03} outlineColor={theme.labelOutline} anchorY="bottom">
              {l.text}
            </Text>
          </Billboard>
        ))}
      </group>
    </group>
  )
})
