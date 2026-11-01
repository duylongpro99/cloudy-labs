// Resource graph -> the Fixture shape the scene layers draw.
// Containment gives each node its parent; an attach-badge kind (security group, Elastic IP) joined by
// an attach-style edge to a host kind (instance, NAT) becomes a badge on it; other edges are lines.
// The root is the account; its regions sit side by side and the global group (IAM and the like) to
// one side, drawn only when it holds something.
// A kind the registry does not know is labelled with its service and id, since its label may be empty.
import { edgeStyleOf, kindView } from '../registry/registry'
import type { Fixture, FixtureAttachment, FixtureEdge, FixtureNode } from '../scene/fixture'
import type { GraphNode, ResourceGraph } from './types'

export interface SceneGraph extends Fixture {
  // Graph node per resource id, for the property panel.
  nodesById: Map<string, GraphNode>
}

// A security group attached to several instances gets one badge per instance; the extra
// badges carry the host in their id. AWS ids never contain "@".
export const resourceId = (placementId: string) => placementId.split('@')[0]

export function graphToScene(g: ResourceGraph): SceneGraph {
  const account = g.nodes.find((n) => n.kind === 'account')
  if (!account) throw new Error('graph has no account node')
  const nodesById = new Map(g.nodes.map((n) => [n.id, n]))
  // A graph without a working emulator shows the account and its region trays alone.
  if (g.status === 'emulator-down') {
    const regions = g.nodes.filter((n) => n.kind === 'region')
    return {
      nodes: [account, ...regions].map((n) => ({ id: n.id, label: n.label, kind: n.kind, parent: n === account ? null : account.id })),
      edges: [],
      attachments: [],
      nodesById: new Map([account, ...regions].map((n) => [n.id, n])),
    }
  }

  const parent = new Map(g.contains.map((c) => [c.child, c.parent]))
  const hostsOf = new Map<string, string[]>()
  for (const e of g.edges) {
    const host = nodesById.get(e.to)
    if (edgeStyleOf(e.kind) !== 'attach' || !host || !kindView(host.kind).host) continue
    hostsOf.set(e.from, [...(hostsOf.get(e.from) ?? []), e.to])
  }

  const hasChildren = new Set(g.contains.map((c) => c.parent))
  const nodes: FixtureNode[] = []
  const attachments: FixtureAttachment[] = []
  for (const n of g.nodes) {
    if (n.kind === 'global' && !hasChildren.has(n.id)) continue // no global resources: no empty tray
    const hosts = hostsOf.get(n.id)
    const view = kindView(n.kind)
    if (view.role === 'attach-badge' && hosts) {
      hosts.sort().forEach((host, i) => attachments.push({ id: i === 0 ? n.id : `${n.id}@${host}`, kind: n.kind, host }))
      continue
    }
    const label = view.fallback ? `${view.service || n.kind} · ${n.id}` : n.label
    nodes.push({ id: n.id, label, kind: n.kind, parent: parent.get(n.id) ?? null })
  }

  const edges: FixtureEdge[] = g.edges
    .filter((e) => edgeStyleOf(e.kind) !== 'attach')
    .map((e) => ({ from: e.from, to: e.to, kind: e.kind, label: e.label }))
  return { nodes, edges, attachments, nodesById }
}
