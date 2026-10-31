// Resource graph as the lab-server sends it. Mirrors server/src/cloudy_labs/graph/schema.py;
// graph-to-scene.test.ts reads the server's golden graph so the two cannot drift apart.
import { REQUIRED_KINDS, type AwsKind } from '../scene/aws-objects'

export type GraphEdgeKind = 'route' | 'association' | 'attached' | 'uses-key'
export type GraphStatus = 'ok' | 'emulator-down'

export interface GraphNode {
  id: string
  kind: AwsKind
  label: string
  props: Record<string, unknown>
}

export interface GraphContains {
  parent: string
  child: string
}

export interface GraphEdge {
  id: string
  kind: GraphEdgeKind
  from: string
  to: string
  label: string
}

export interface ResourceGraph {
  version: number
  takenAt: string
  emulator: 'floci'
  status: GraphStatus
  nodes: GraphNode[]
  contains: GraphContains[]
  edges: GraphEdge[]
  warnings: string[]
}

// One AWS API call that went through api-tap.
export interface ApiEvent {
  service: string
  action: string
  seq: number
  write: boolean // changes state; only these fly to the scene
}

// Twin mode (PRD F6): the open lab's checks and the parts of its target architecture not built
// yet. Mirrors TwinState in server/src/cloudy_labs/twin.py; merge-twin.test.ts reads the golden twin.
export type CheckStatus = 'passed' | 'failed' | 'pending' // pending: not run against the current state

export interface TwinCheck {
  id: string
  task: string
  description: string
  status: CheckStatus
  message: string
  resourceIds: string[]
}

export interface TwinGhost {
  id: string // "ghost:" + target node id
  kind: AwsKind
  label: string
  parent: string // a ghost id, or the id of the real resource its parent is bound to
  checks: string[]
}

export interface TwinState {
  lab: string | null // null: no lab is open
  attempt: number | null
  checks: TwinCheck[]
  ghosts: TwinGhost[]
  bound: Record<string, string> // target node id -> real resource id
}

export type ServerMessage =
  | { type: 'graph'; graph: ResourceGraph }
  | { type: 'twin'; twin: TwinState }
  | ({ type: 'api-event' } & ApiEvent)

const CHECK_STATUSES: readonly CheckStatus[] = ['passed', 'failed', 'pending']
const EDGE_KINDS: readonly GraphEdgeKind[] = ['route', 'association', 'attached', 'uses-key']

// Minimal shape check: enough to fail loudly on a schema mismatch instead of drawing garbage.
export function parseGraph(json: unknown): ResourceGraph {
  const g = json as Partial<ResourceGraph> | null
  if (!g || typeof g !== 'object') throw new Error('graph: not an object')
  for (const key of ['nodes', 'contains', 'edges', 'warnings'] as const) {
    if (!Array.isArray(g[key])) throw new Error(`graph: missing array "${key}"`)
  }
  if (typeof g.version !== 'number') throw new Error('graph: missing "version"')
  if (g.status !== 'ok' && g.status !== 'emulator-down') throw new Error(`graph: unknown status ${String(g.status)}`)
  for (const n of g.nodes!) {
    if (!REQUIRED_KINDS.includes(n.kind)) throw new Error(`graph: node ${n.id} has unknown kind ${n.kind}`)
  }
  for (const e of g.edges!) {
    if (!EDGE_KINDS.includes(e.kind)) throw new Error(`graph: edge ${e.id} has unknown kind ${e.kind}`)
  }
  return g as ResourceGraph
}

export function parseTwin(json: unknown): TwinState {
  const t = json as Partial<TwinState> | null
  if (!t || typeof t !== 'object') throw new Error('twin: not an object')
  if (!Array.isArray(t.checks) || !Array.isArray(t.ghosts)) throw new Error('twin: missing "checks" or "ghosts"')
  if (!t.bound || typeof t.bound !== 'object') throw new Error('twin: missing "bound"')
  for (const c of t.checks) {
    if (!CHECK_STATUSES.includes(c.status)) throw new Error(`twin: check ${c.id} has unknown status ${c.status}`)
  }
  for (const g of t.ghosts) {
    if (!REQUIRED_KINDS.includes(g.kind) || g.kind === 'region') throw new Error(`twin: ghost ${g.id} has unknown kind ${g.kind}`)
  }
  return t as TwinState
}
