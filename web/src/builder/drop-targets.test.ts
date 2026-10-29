import { describe, expect, it } from 'vitest'
import { TRAY_H, type LaidOutGroup } from '../scene/layout'
import { dropTarget, traysUnder } from './drop-targets'
import { op } from './test-fixtures'

const tray = (id: string, kind: string, level: number, x: number, z: number, w: number, d: number): LaidOutGroup =>
  ({ node: { id, kind, label: id }, kind, level, x, z, w, d, y: level * 0.18 }) as unknown as LaidOutGroup

const region = tray('us-east-1', 'region', 0, 0, 0, 20, 20)
const vpc = tray('vpc-1', 'vpc', 1, 2, 2, 10, 10)
const az = tray('vpc-1/us-east-1a', 'az', 2, 3, 3, 5, 5)
const pub = tray('subnet-1', 'subnet-public', 3, 4, 4, 2, 2)
const ALL = [region, vpc, az, pub]
const down = [0, -1, 0] as const

describe('traysUnder', () => {
  it('returns every tray under a vertical ray, deepest first', () => {
    expect(traysUnder(ALL, [5, 10, 5], down).map((t) => t.node.id)).toEqual(['subnet-1', 'vpc-1/us-east-1a', 'vpc-1', 'us-east-1'])
  })

  it('misses trays the ray passes beside', () => {
    expect(traysUnder(ALL, [15, 10, 15], down).map((t) => t.node.id)).toEqual(['us-east-1'])
    expect(traysUnder(ALL, [30, 10, 30], down)).toEqual([])
  })

  it('meets each tray on its own top face along a slanted ray', () => {
    // Aimed at the region's top face at x=1; the VPC's face sits higher, so the ray meets it earlier, at x<2.
    const origin = [1 + 10 - TRAY_H, 10, 5] as const
    const dir = [-1, -1, 0] as const
    expect(traysUnder([region, vpc], origin, dir).map((t) => t.node.id)).toEqual(['us-east-1'])
  })

  it('finds nothing for a ray parallel to the ground', () => {
    expect(traysUnder(ALL, [5, 10, 5], [1, 0, 0])).toEqual([])
  })
})

describe('dropTarget', () => {
  it('chooses the deepest tray that may hold the resource', () => {
    const hits = traysUnder(ALL, [5, 10, 5], down)
    const subnet = dropTarget(op('create-subnet'), hits)
    expect(subnet.ok && subnet.tray.node.id).toBe('vpc-1/us-east-1a')
    const nat = dropTarget(op('create-nat-gateway'), hits)
    expect(nat.ok && nat.tray.node.id).toBe('subnet-1')
    const vpcDrop = dropTarget(op('create-vpc'), hits)
    expect(vpcDrop.ok && vpcDrop.tray.node.id).toBe('us-east-1')
  })

  it('explains a drop on the wrong kind of tray', () => {
    const r = dropTarget(op('create-nat-gateway'), traysUnder(ALL, [7, 10, 7], down))
    expect(r).toEqual({ ok: false, reason: expect.stringContaining('không đặt được vào Availability Zone') })
    expect(!r.ok && r.reason).toContain('subnet công khai')
  })

  it('explains a drop outside every tray', () => {
    const r = dropTarget(op('create-route-table'), [])
    expect(!r.ok && r.reason).toBe('Thả Route Table vào một VPC trong cảnh')
  })
})
