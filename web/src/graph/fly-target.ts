// Which node an API call "flies" to (PRD F3.6): the node of the kind the action names that the
// next graph added, else one whose props changed, else one it removed. null means the region tray.
import type { AwsKind } from '../scene/aws-objects'
import type { SceneGraph } from './graph-to-scene'

// The first noun the action name contains wins.
const ACTION_KINDS: [string, AwsKind[]][] = [
  ['Vpc', ['vpc']],
  ['Subnet', ['subnet-public', 'subnet-private']],
  ['InternetGateway', ['igw']],
  ['NatGateway', ['nat']],
  ['Route', ['route-table']],
  ['SecurityGroup', ['security-group']],
  ['Address', ['elastic-ip']],
  ['KeyPair', ['key-pair']],
  ['Instance', ['instance']],
]

export function actionKinds(action: string): AwsKind[] {
  return ACTION_KINDS.find(([noun]) => action.includes(noun))?.[1] ?? []
}

export function flyTarget(action: string, before: SceneGraph, after: SceneGraph): string | null {
  const kinds = new Set<string>(actionKinds(action))
  const of = (g: SceneGraph) => [...g.nodesById.values()].filter((n) => kinds.has(n.kind))
  const was = new Map(of(before).map((n) => [n.id, n]))
  const now = of(after)
  // The newest added node: ids are random, so "newest" is the last one in the graph's own order.
  const added = now.filter((n) => !was.has(n.id)).at(-1)
  if (added) return added.id
  const changed = now.find((n) => JSON.stringify(n.props) !== JSON.stringify(was.get(n.id)!.props))
  if (changed) return changed.id
  const nowIds = new Set(now.map((n) => n.id))
  return [...was.keys()].find((id) => !nowIds.has(id)) ?? null
}

// A short label for the particle: the action name, capped in length.
export const flyLabel = (action: string) => (action.length > 22 ? `${action.slice(0, 21)}…` : action)
