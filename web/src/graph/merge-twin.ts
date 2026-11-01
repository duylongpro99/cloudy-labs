// Draws the lab's target architecture into the scene (PRD F6.2): each ghost the twin sends
// becomes a node nested where the target puts it, and real resources a target node is bound to
// are marked achieved. Ghosts are always nodes of their own: a ghost security group or Elastic IP
// has nothing real to sit on as a badge.
import type { FixtureAttachment, FixtureNode } from '../scene/fixture'
import { resourceId, type SceneGraph } from './graph-to-scene'
import type { TwinState } from './types'

export interface TwinScene {
  scene: SceneGraph
  achieved: Set<string> // real resource ids in the scene that a target node is bound to
}

export function mergeTwin(scene: SceneGraph, twin: TwinState | null, showGhosts: boolean): TwinScene {
  if (!twin || (twin.ghosts.length === 0 && Object.keys(twin.bound).length === 0)) return { scene, achieved: new Set() }
  const real = new Set(scene.nodes.map((n) => n.id))
  // An attached security group or Elastic IP is a badge, not a node, and one badge per host.
  const badged = new Set(scene.attachments.map((a) => resourceId(a.id)))
  const achieved = new Set(Object.values(twin.bound).filter((id) => real.has(id) || badged.has(id)))
  const nodes: FixtureNode[] = scene.nodes.map((n) => (achieved.has(n.id) ? { ...n, achieved: true } : n))
  const attachments: FixtureAttachment[] = scene.attachments.map((a) => (achieved.has(resourceId(a.id)) ? { ...a, achieved: true } : a))
  if (showGhosts) {
    const root = scene.nodes.find((n) => n.parent === null)!.id
    const region = scene.nodes.find((n) => n.kind === 'region')?.id ?? root
    const known = new Set([...real, ...twin.ghosts.map((g) => g.id)])
    for (const g of twin.ghosts) {
      // The global group is left out of the scene while empty; a ghost of a global kind brings it back.
      const hidden = scene.nodesById.get(g.parent)
      if (!known.has(g.parent) && hidden?.kind === 'global') {
        nodes.push({ id: hidden.id, label: hidden.label, kind: 'global', parent: root })
        known.add(hidden.id)
      }
      // A real parent can vanish between the graph and the twin that follows it (a delete).
      const parent = known.has(g.parent) ? g.parent : region
      nodes.push({ id: g.id, label: g.label, kind: g.kind as FixtureNode['kind'], parent, ghost: true })
    }
  }
  return { scene: { ...scene, nodes, attachments }, achieved }
}

export const withoutGhosts = (scene: SceneGraph): SceneGraph =>
  scene.nodes.some((n) => n.ghost) ? { ...scene, nodes: scene.nodes.filter((n) => !n.ghost) } : scene
