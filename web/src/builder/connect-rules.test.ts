import { describe, expect, it } from 'vitest'
import { connectOp, connectOpsFrom } from './connect-rules'
import { OPS, golden, node } from './test-fixtures'

const g = golden()
const freeIgw = { id: 'igw-new', kind: 'igw', label: 'lab06-igw-2', props: {} } as const
const pendingNat = { ...node(g, 'nat-235f142ec41b5d904'), props: { state: 'pending' } }

describe('connectOp', () => {
  it('offers edges only from kinds that have them', () => {
    expect(connectOpsFrom(OPS, 'route-table').map((o) => o.name)).toEqual(['create-route', 'associate-route-table'])
    expect(connectOpsFrom(OPS, 'vpc')).toEqual([])
  })

  it('turns an IGW → VPC edge into attach-internet-gateway', () => {
    const r = connectOp(OPS, freeIgw, node(g, 'vpc-149d0439'))
    expect(r.ok && r.op.name).toBe('attach-internet-gateway')
    expect(r.ok && r.params).toEqual({ igwId: 'igw-new', vpcId: 'vpc-149d0439' })
  })

  it('turns route table → IGW or NAT into a default route', () => {
    for (const target of ['igw-34ddd4cd', 'nat-235f142ec41b5d904']) {
      const r = connectOp(OPS, node(g, 'rtb-02888668'), node(g, target))
      expect(r.ok && r.op.name).toBe('create-route')
      expect(r.ok && r.params).toEqual({ routeTableId: 'rtb-02888668', targetId: target, destination: '0.0.0.0/0' })
    }
  })

  it('turns route table → subnet into an association', () => {
    for (const subnet of ['subnet-83a1f79a', 'subnet-44acdeb7']) {
      const r = connectOp(OPS, node(g, 'rtb-509e5b33'), node(g, subnet))
      expect(r.ok && r.op.name).toBe('associate-route-table')
      expect(r.ok && r.params).toEqual({ routeTableId: 'rtb-509e5b33', subnetId: subnet })
    }
  })

  it('refuses pairs no op connects', () => {
    const igwSubnet = connectOp(OPS, freeIgw, node(g, 'subnet-83a1f79a'))
    expect(!igwSubnet.ok && igwSubnet.reason).toContain('chỉ nối tới VPC')
    const rtVpc = connectOp(OPS, node(g, 'rtb-509e5b33'), node(g, 'vpc-149d0439'))
    expect(!rtVpc.ok && rtVpc.reason).toContain('Route Table không nối được tới VPC')
    const fromVpc = connectOp(OPS, node(g, 'vpc-149d0439'), node(g, 'igw-34ddd4cd'))
    expect(!fromVpc.ok && fromVpc.reason).toContain('không có cạnh nào')
  })

  it('refuses an IGW that is already attached, and a NAT that is not available yet', () => {
    const attached = connectOp(OPS, node(g, 'igw-34ddd4cd'), node(g, 'vpc-149d0439'))
    expect(!attached.ok && attached.reason).toContain('đã gắn vào vpc-149d0439')
    const pending = connectOp(OPS, node(g, 'rtb-02888668'), pendingNat)
    expect(!pending.ok && pending.reason).toContain('đang pending')
  })
})
