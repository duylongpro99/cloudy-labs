// Lights up what the selected check looks at (PRD F6.3): an outline on each of its objects and
// badges, a tint on each of its trays, and a dimmed cover on every tray that holds none of them.
// Drawn as planes just above the trays, like DropHighlight, so TrayLayer's own fades stay untouched.
import { useMemo } from 'react'
import type { SceneGraph } from '../graph/graph-to-scene'
import { HighlightOverlay } from './aws-objects/highlight-overlay'
import type { AwsObjectPlacement } from './aws-objects'
import { TRAY_H, type LaidOutGroup } from './layout'
import type { Theme } from './theme'

// Every id in `ids`, and every tray that holds one of them.
export function withContainers(ids: ReadonlySet<string>, scene: SceneGraph): Set<string> {
  const parent = new Map(scene.nodes.map((n) => [n.id, n.parent]))
  const host = new Map(scene.attachments.map((a) => [a.id, a.host]))
  const out = new Set<string>()
  for (const id of ids) {
    out.add(id)
    let cur = host.get(id) ?? parent.get(id)
    while (cur != null && !out.has(cur)) {
      out.add(cur)
      cur = parent.get(cur)
    }
  }
  return out
}

export function CheckHighlight({ highlighted, scene, groups, placements, theme }: {
  highlighted: ReadonlySet<string>
  scene: SceneGraph
  groups: readonly LaidOutGroup[]
  placements: readonly AwsObjectPlacement[]
  theme: Theme
}) {
  const kept = useMemo(() => withContainers(highlighted, scene), [highlighted, scene])
  if (highlighted.size === 0) return null
  return (
    <group userData={{ checkHighlight: true }}>
      {groups.map((g) => {
        const on = highlighted.has(g.node.id)
        if (!on && kept.has(g.node.id)) return null
        return (
          <mesh key={g.node.id} position={[g.x + g.w / 2, g.y + TRAY_H + 0.02, g.z + g.d / 2]} rotation-x={-Math.PI / 2} renderOrder={g.level + 0.7}>
            <planeGeometry args={[g.w, g.d]} />
            <meshBasicMaterial color={on ? theme.checkHighlight : theme.background} transparent opacity={on ? 0.28 : 0.55} depthWrite={false} toneMapped={false} />
          </mesh>
        )
      })}
      {placements
        .filter((p) => highlighted.has(p.id))
        .map((p) => (
          <HighlightOverlay key={p.id} target={p} color={theme.checkHighlight} thickness={0.09} />
        ))}
    </group>
  )
}
