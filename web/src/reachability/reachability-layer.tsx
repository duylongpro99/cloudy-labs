// Draws a reachability result in the scene: a static line through the hops that are objects in the
// scene, each numbered as in the panel; the hop that stops the flow is red. No moving packets: the
// result is an analysis of configuration, not traffic (PRD principle 3).
import { Billboard, Line, Text } from '@react-three/drei'
import { memo, useMemo } from 'react'
import type { EdgeAnchor } from '../scene/object-placements'
import type { Theme } from '../scene/theme'
import { FONT } from '../scene/tray-layer'
import type { ReachHop } from './reachability-api'

export const PATH_RISE = 1.1 // above the objects' tops, clear of the edge lines

export interface PathPoint {
  id: string
  n: number // the hop's number in the panel (1-based)
  at: [number, number, number]
  blocked: boolean
}

// One point per hop that has an object in the scene, in hop order; a hop repeating the previous
// object (an ENI and its instance's group, say) adds no point but keeps its number for the label.
export function pathPoints(hops: readonly ReachHop[], anchors: ReadonlyMap<string, EdgeAnchor>): PathPoint[] {
  const out: PathPoint[] = []
  hops.forEach((h, i) => {
    const a = anchors.get(h.resource_id)
    if (!a) return
    const blocked = h.verdict === 'deny'
    const last = out[out.length - 1]
    if (last && last.id === h.resource_id) {
      last.blocked ||= blocked
      return
    }
    out.push({ id: h.resource_id, n: i + 1, at: [a.at[0], a.at[1] + PATH_RISE, a.at[2]], blocked })
  })
  return out
}

export const ReachabilityLayer = memo(function ReachabilityLayer({ hops, anchors, theme }: {
  hops: readonly ReachHop[]
  anchors: ReadonlyMap<string, EdgeAnchor>
  theme: Theme
}) {
  const points = useMemo(() => pathPoints(hops, anchors), [hops, anchors])
  if (points.length === 0) return null
  return (
    <group userData={{ reachability: true }}>
      {points.length > 1 && (
        <Line points={points.map((p) => p.at)} color={theme.checkHighlight} lineWidth={3} depthTest={false} renderOrder={21} />
      )}
      {points.map((p) => (
        <Billboard key={`${p.id}-${p.n}`} position={p.at}>
          <mesh renderOrder={22}>
            <circleGeometry args={[0.28, 24]} />
            <meshBasicMaterial color={p.blocked ? theme.failed : theme.checkHighlight} depthTest={false} toneMapped={false} />
          </mesh>
          <Text font={FONT} fontSize={0.3} color={theme.background} anchorX="center" anchorY="middle" position={[0, 0, 0.01]} renderOrder={23}>
            {p.blocked ? '✗' : String(p.n)}
          </Text>
        </Billboard>
      ))}
    </group>
  )
})
