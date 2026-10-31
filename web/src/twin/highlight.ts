// What the scene lights up for one check (PRD F6.3): the resources the check reported, as the
// scene draws them (a security group or Elastic IP badge carries its host in its id), and the
// ghosts of the target nodes that wait on the check, when the scene shows them.
import { resourceId, type SceneGraph } from '../graph/graph-to-scene'
import type { TwinState } from '../graph/types'

export function highlightFor(checkId: string, twin: TwinState | null, scene: SceneGraph): Set<string> {
  const out = new Set<string>()
  const check = twin?.checks.find((c) => c.id === checkId)
  if (!twin || !check) return out
  const ids = new Set(check.resourceIds)
  for (const n of scene.nodes) if (ids.has(n.id)) out.add(n.id)
  for (const a of scene.attachments) if (ids.has(resourceId(a.id))) out.add(a.id)
  const shown = new Set(scene.nodes.map((n) => n.id))
  for (const g of twin.ghosts) if (g.checks.includes(checkId) && shown.has(g.id)) out.add(g.id)
  return out
}
