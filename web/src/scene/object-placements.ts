// Turns the laid-out fixture into object placements: blocks for leaves, badges on trays,
// and attachment badges on their host blocks.
import type { AwsKind, AwsObjectPlacement } from './aws-objects'
import { attachPosition, MANIFEST_BY_KIND, objectHeight, trayBadgePosition, type Vec3 } from './aws-objects'
import type { Fixture } from './fixture'
import type { Layout } from './layout'
import { TRAY_H } from './layout'

export function scenePlacements(fixture: Fixture, layout: Layout): AwsObjectPlacement[] {
  const out: AwsObjectPlacement[] = []
  for (const g of layout.groups) {
    if (MANIFEST_BY_KIND[g.kind].role !== 'tray-badge') continue
    out.push({ id: g.node.id, kind: g.kind, position: trayBadgePosition(g, g.y + TRAY_H) })
  }
  const hosts = new Map<string, AwsObjectPlacement>()
  for (const l of layout.leaves) {
    const p: AwsObjectPlacement = { id: l.node.id, kind: l.node.kind as AwsKind, position: [l.x, l.y, l.z] }
    hosts.set(p.id, p)
    out.push(p)
  }
  const slots = new Map<string, number>()
  for (const a of fixture.attachments) {
    const host = hosts.get(a.host)
    if (!host) throw new Error(`attachment ${a.id} has no host ${a.host}`)
    const slot = slots.get(a.host) ?? 0
    slots.set(a.host, slot + 1)
    out.push({ id: a.id, kind: a.kind, position: attachPosition(host, slot) })
  }
  return out
}

// Where an edge meets each object: the centre of its top face. Groups are reached through their tray badge.
export interface EdgeAnchor {
  at: Vec3
  kind: AwsKind
}

export function edgeAnchors(placements: readonly AwsObjectPlacement[]): Map<string, EdgeAnchor> {
  return new Map(placements.map((p) => [p.id, { at: [p.position[0], p.position[1] + objectHeight(p.kind), p.position[2]], kind: p.kind }]))
}
