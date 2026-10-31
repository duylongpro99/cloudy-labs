// Seeded 200-node resource graph for the benchmark, so it draws through the same
// graph -> graphToScene -> layout path as the live view.
// It is the M0 benchmark fixture re-expressed as a graph (same distribution, so results compare):
// parents become `contains`, badges become security group / Elastic IP nodes with `attached` edges,
// and the fixture's lines become 0.0.0.0/0 routes.
import { buildFixture } from '../scene/fixture'
import type { GraphEdge, GraphNode, ResourceGraph, TwinGhost, TwinState } from './types'

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

// A twin over the synthetic graph for the benchmark: `count` ghosts (an instance and a route table
// left to build in each subnet and VPC, cycling) and every VPC and subnet marked achieved.
export function syntheticTwin(graph: ResourceGraph, count: number): TwinState {
  const subnets = graph.nodes.filter((n) => n.kind === 'subnet-public' || n.kind === 'subnet-private')
  const vpcs = graph.nodes.filter((n) => n.kind === 'vpc')
  const ghosts = Array.from({ length: count }, (_, i) => {
    const vpc = i % 4 === 3
    const parent = vpc ? vpcs[i % vpcs.length] : subnets[i % subnets.length]
    return { id: `ghost:t-${i}`, kind: vpc ? 'route-table' : 'instance', label: `Mục tiêu ${i + 1}`, parent: parent.id, checks: [] }
  }) as TwinGhost[]
  const bound = Object.fromEntries([...vpcs, ...subnets].map((n) => [`t-${n.id}`, n.id]))
  return { lab: 'bench', attempt: 1, checks: [], ghosts, bound }
}
