// Seeded 200-node resource graph for the benchmark, so it draws through the same
// graph -> graphToScene -> layout path as the live view.
// It is the M0 benchmark fixture re-expressed as a graph (same distribution, so results compare):
// parents become `contains`, badges become security group / Elastic IP nodes with `attached` edges,
// and the fixture's lines become 0.0.0.0/0 routes.
import { buildFixture } from '../scene/fixture'
import type { GraphEdge, GraphNode, ResourceGraph } from './types'

export function syntheticGraph(seed = 42): ResourceGraph {
  const f = buildFixture(seed)
  const nodes: GraphNode[] = [
    ...f.nodes.map((n) => ({ id: n.id, kind: n.kind, label: n.label, props: {} })),
    ...f.attachments.map((a) => ({ id: a.id, kind: a.kind, label: a.id, props: {} })),
  ]
  const contains = f.nodes.flatMap((n) => (n.parent ? [{ parent: n.parent, child: n.id }] : []))
  const edges: GraphEdge[] = [
    ...f.attachments.map((a) => ({ id: `attached:${a.id}`, kind: 'attached' as const, from: a.id, to: a.host, label: '' })),
    ...f.edges.map((e, i) => ({ id: `route:${i}`, kind: 'route' as const, from: e.from, to: e.to, label: '0.0.0.0/0' })),
  ]
  return { version: 1, takenAt: '', emulator: 'floci', status: 'ok', nodes, contains, edges, warnings: [] }
}
