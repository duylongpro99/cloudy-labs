// Configuration edges as raised Bezier curves (one merged draw call),
// plus instanced pulse particles travelling along them.
import { Line } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import { Color, InstancedMesh, Object3D, QuadraticBezierCurve3, Vector3 } from 'three'
import type { FixtureEdge } from '../fixture'
import type { LaidOutLeaf } from './layout'
import type { Theme } from './theme'

const SEGMENTS = 20
const PULSE_SPEED = 0.35 // curve lengths per second

export function EdgeLayer({ edges, leaves, theme }: { edges: FixtureEdge[]; leaves: LaidOutLeaf[]; theme: Theme }) {
  const curves = useMemo(() => {
    const at = new Map(leaves.map((l) => [l.node.id, l]))
    return edges.map(({ from, to }) => {
      const a = at.get(from)!
      const b = at.get(to)!
      const start = new Vector3(a.x, a.y + 0.9, a.z)
      const end = new Vector3(b.x, b.y + 0.6, b.z)
      const mid = start.clone().add(end).multiplyScalar(0.5)
      mid.y += 1 + start.distanceTo(end) * 0.18
      return new QuadraticBezierCurve3(start, mid, end)
    })
  }, [edges, leaves])

  // Segment pairs for LineSegments2: every curve becomes SEGMENTS short segments.
  const points = useMemo(() => {
    const out: Vector3[] = []
    for (const c of curves) {
      const pts = c.getPoints(SEGMENTS)
      for (let i = 0; i < pts.length - 1; i++) out.push(pts[i], pts[i + 1])
    }
    return out
  }, [curves])

  const pulses = useRef<InstancedMesh>(null)
  const dummy = useMemo(() => new Object3D(), [])
  const tmp = useMemo(() => new Vector3(), [])
  useFrame(({ clock }) => {
    const mesh = pulses.current
    if (!mesh) return
    const t = clock.getElapsedTime() * PULSE_SPEED
    curves.forEach((c, i) => {
      c.getPoint((t + i * 0.137) % 1, tmp)
      dummy.position.copy(tmp)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <group>
      <Line points={points} segments color={theme.edge} lineWidth={1.6} transparent opacity={0.85} />
      <instancedMesh ref={pulses} args={[undefined, undefined, curves.length]} frustumCulled={false}>
        <sphereGeometry args={[0.14, 12, 8]} />
        <meshBasicMaterial color={new Color(theme.pulse)} toneMapped={false} />
      </instancedMesh>
    </group>
  )
}
