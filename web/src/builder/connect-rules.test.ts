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

describe('security group → instance', () => {
  it('becomes modify-instance-attribute', () => {
    const r = connectOp(OPS, node(g, 'sg-b58b05ddff613fe13'), node(g, 'i-fdb553d289095d128'), g.edges)
    expect(r.ok && r.op.name).toBe('modify-instance-attribute')
    expect(r.ok && r.params).toEqual({ instanceId: 'i-fdb553d289095d128', groupId: 'sg-b58b05ddff613fe13' })
  })

  it('refuses a group the instance already has, and other kinds', () => {
    const again = connectOp(OPS, node(g, 'sg-dbd2e6007fa2e7eef'), node(g, 'i-fdb553d289095d128'), g.edges)
    expect(!again.ok && again.reason).toContain('lab07-web đã gắn vào lab07-web')
    const toSubnet = connectOp(OPS, node(g, 'sg-b58b05ddff613fe13'), node(g, 'subnet-83a1f79a'), g.edges)
    expect(!toSubnet.ok && toSubnet.reason).toContain('chỉ nối tới EC2 Instance')
  })
})
