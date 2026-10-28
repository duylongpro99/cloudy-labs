// Deterministic layout computed bottom-up from the containment tree (PRD F3.3):
// leaves sit on a grid inside their subnet, and each group is sized from its children.
import type { Fixture, FixtureNode, GroupKind } from '../fixture'

export const CELL = 2.2 // leaf footprint incl. gap
export const BLOCK = 1.4 // leaf block width
export const TRAY_H = 0.16 // tray thickness
export const LEVEL_RISE = 0.18 // each nesting level sits slightly higher
const PAD = 0.9
const LABEL_STRIP = 1.2 // room for the flat group label along the near edge
const GAP = 0.8

export interface Box {
  x: number
  z: number
  w: number
  d: number
}

export interface LaidOutGroup extends Box {
  node: FixtureNode
  kind: GroupKind
  level: number
  y: number
}

export interface LaidOutLeaf {
  node: FixtureNode
  x: number
  z: number
  y: number
}

export interface Layout {
  groups: LaidOutGroup[]
  leaves: LaidOutLeaf[]
  bounds: Box
}

const isGroup = (n: FixtureNode) => ['region', 'vpc', 'az', 'subnet-public', 'subnet-private'].includes(n.kind)

export function computeLayout(f: Fixture): Layout {
  const children = new Map<string, FixtureNode[]>()
  for (const n of f.nodes) if (n.parent) children.set(n.parent, [...(children.get(n.parent) ?? []), n])

  // Pass 1 (bottom-up): size of every group.
  const size = new Map<string, { w: number; d: number }>()
  const measure = (n: FixtureNode): { w: number; d: number } => {
    const kids = children.get(n.id) ?? []
    const leaves = kids.filter((k) => !isGroup(k))
    const groups = kids.filter(isGroup)
    const cols = Math.max(1, Math.ceil(Math.sqrt(leaves.length)))
    const rows = Math.ceil(leaves.length / cols)
    const leafW = leaves.length ? cols * CELL : 0
    const leafD = leaves.length ? rows * CELL : 0
    const sub = groups.map(measure)
    // AZ stacks subnets front-to-back; everything else lays groups left-to-right.
    const stack = n.kind === 'az'
    const gW = stack ? Math.max(0, ...sub.map((s) => s.w)) : sub.reduce((a, s) => a + s.w, 0) + GAP * Math.max(0, sub.length - 1)
    const gD = stack ? sub.reduce((a, s) => a + s.d, 0) + GAP * Math.max(0, sub.length - 1) : Math.max(0, ...sub.map((s) => s.d))
    const w = Math.max(leafW, gW) + PAD * 2
    const d = leafD + (leafD && gD ? GAP : 0) + gD + PAD * 2 + LABEL_STRIP
    const s = { w, d }
    size.set(n.id, s)
    return s
  }
  const root = f.nodes.find((n) => n.parent === null)!
  measure(root)

  // Pass 2 (top-down): positions. x/z are the group's min corner.
  const groups: LaidOutGroup[] = []
  const leaves: LaidOutLeaf[] = []
  const place = (n: FixtureNode, x: number, z: number, level: number) => {
    const { w, d } = size.get(n.id)!
    const y = level * LEVEL_RISE
    groups.push({ node: n, kind: n.kind as GroupKind, level, x, z, w, d, y })
    const kids = children.get(n.id) ?? []
    const leafKids = kids.filter((k) => !isGroup(k))
    const cols = Math.max(1, Math.ceil(Math.sqrt(leafKids.length)))
    leafKids.forEach((k, i) => {
      leaves.push({
        node: k,
        x: x + PAD + (i % cols) * CELL + CELL / 2,
        z: z + PAD + Math.floor(i / cols) * CELL + CELL / 2,
        y: y + TRAY_H,
      })
    })
    const leafD = leafKids.length ? Math.ceil(leafKids.length / cols) * CELL + GAP : 0
    let cx = x + PAD
    let cz = z + PAD + leafD
    for (const g of kids.filter(isGroup)) {
      const s = size.get(g.id)!
      place(g, cx, cz, level + 1)
      if (n.kind === 'az') cz += s.d + GAP
      else cx += s.w + GAP
    }
  }
  place(root, 0, 0, 0)

  // Centre everything on the origin.
  const r = groups[0]
  const ox = r.w / 2
  const oz = r.d / 2
  for (const g of groups) (g.x -= ox), (g.z -= oz)
  for (const l of leaves) (l.x -= ox), (l.z -= oz)
  return { groups, leaves, bounds: { x: -ox, z: -oz, w: r.w, d: r.d } }
}
