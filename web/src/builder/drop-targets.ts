// Where a resource dragged from the palette may be dropped (PRD F4.2). The table itself comes
// from the server's op catalogue (`containers` of each create op), so both sides agree.
import { TRAY_H, type LaidOutGroup } from '../scene/layout'
import type { OpSpec } from './builder-api'

export type Vec3 = readonly [number, number, number]

export const KIND_LABEL: Record<string, string> = {
  region: 'Region',
  vpc: 'VPC',
  az: 'Availability Zone',
  subnet: 'Subnet',
  'subnet-public': 'subnet công khai',
  'subnet-private': 'subnet riêng tư',
  igw: 'Internet Gateway',
  'elastic-ip': 'Elastic IP',
  nat: 'NAT Gateway',
  'route-table': 'Route Table',
  'security-group': 'Security Group',
  'key-pair': 'Key Pair',
  instance: 'EC2 Instance',
}

export const kindLabel = (kind: string) => KIND_LABEL[kind] ?? kind

// Trays whose top face the ray crosses inside the tray's outline, deepest first.
export function traysUnder(groups: readonly LaidOutGroup[], origin: Vec3, dir: Vec3): LaidOutGroup[] {
  if (dir[1] === 0) return []
  const hits = groups.filter((g) => {
    const t = (g.y + TRAY_H - origin[1]) / dir[1]
    const x = origin[0] + t * dir[0]
    const z = origin[2] + t * dir[2]
    return x >= g.x && x <= g.x + g.w && z >= g.z && z <= g.z + g.d
  })
  return hits.sort((a, b) => b.level - a.level)
}

export const createOpFor = (ops: readonly OpSpec[], kind: string) => ops.find((o) => o.gesture === 'create' && o.creates === kind)

export const acceptsDrop = (op: OpSpec, trayKind: string) => (op.containers ?? []).includes(trayKind)

export type DropCheck = { ok: true; tray: LaidOutGroup } | { ok: false; reason: string }

// The deepest tray under the pointer that may hold the resource, or why there is none.
export function dropTarget(op: OpSpec, hits: readonly LaidOutGroup[]): DropCheck {
  const tray = hits.find((h) => acceptsDrop(op, h.kind))
  if (tray) return { ok: true, tray }
  const where = (op.containers ?? []).map(kindLabel).join(' hoặc ')
  const what = kindLabel(op.creates ?? '')
  if (hits.length === 0) return { ok: false, reason: `Thả ${what} vào một ${where} trong cảnh` }
  return { ok: false, reason: `${what} không đặt được vào ${kindLabel(hits[0].kind)}: nó phải nằm trong ${where}` }
}
