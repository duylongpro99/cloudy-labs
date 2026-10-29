// Resource graph -> the Fixture shape the scene layers draw.
// Containment gives each node its parent; security groups and Elastic IPs attached to a block
// become badges on it; route, association and uses-key edges are drawn as lines.
import type { Fixture, FixtureAttachment, FixtureEdge, FixtureNode } from '../scene/fixture'
import type { GraphNode, ResourceGraph } from './types'

export interface SceneGraph extends Fixture {
  // Graph node per resource id, for the property panel.
  nodesById: Map<string, GraphNode>
}

const HOST_KINDS = new Set<string>(['instance', 'nat'])

// A security group attached to several instances gets one badge per instance; the extra
// badges carry the host in their id. AWS ids never contain "@".
export const resourceId = (placementId: string) => placementId.split('@')[0]

export function graphToScene(g: ResourceGraph): SceneGraph {
  const region = g.nodes.find((n) => n.kind === 'region')
  if (!region) throw new Error('graph has no region node')
  const nodesById = new Map(g.nodes.map((n) => [n.id, n]))
  // A graph without a working emulator shows the region tray alone.
  if (g.status === 'emulator-down') {
    return { nodes: [{ id: region.id, label: region.label, kind: 'region', parent: null }], edges: [], attachments: [], nodesById: new Map([[region.id, region]]) }
  }

  const parent = new Map(g.contains.map((c) => [c.child, c.parent]))
  const hostsOf = new Map<string, string[]>()
  for (const e of g.edges) {
    if (e.kind !== 'attached' || !HOST_KINDS.has(nodesById.get(e.to)?.kind ?? '')) continue
    hostsOf.set(e.from, [...(hostsOf.get(e.from) ?? []), e.to])
  }

  const nodes: FixtureNode[] = []
  const attachments: FixtureAttachment[] = []
  for (const n of g.nodes) {
    const hosts = hostsOf.get(n.id)
    if ((n.kind === 'security-group' || n.kind === 'elastic-ip') && hosts) {
      hosts.sort().forEach((host, i) => attachments.push({ id: i === 0 ? n.id : `${n.id}@${host}`, kind: n.kind as FixtureAttachment['kind'], host }))
      continue
    }
    nodes.push({ id: n.id, label: n.label, kind: n.kind as FixtureNode['kind'], parent: parent.get(n.id) ?? null })
  }

  const edges: FixtureEdge[] = g.edges
    .filter((e) => e.kind !== 'attached')
    .map((e) => ({ from: e.from, to: e.to, kind: e.kind as FixtureEdge['kind'], label: e.label }))
  return { nodes, edges, attachments, nodesById }
}
