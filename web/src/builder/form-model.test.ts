import { describe, expect, it } from 'vitest'
import type { ResourceGraph } from '../graph/types'
import { createDraft, fixedDraft, freeElasticIps, groupsIn, ingressDraft, nextFreeSubnet, suggestName, vpcOf } from './form-model'
import { LAB, LAB07, golden, op } from './test-fixtures'

const g = golden()
const empty: ResourceGraph = { ...g, nodes: g.nodes.filter((n) => n.kind === 'region'), contains: [], edges: [] }
const region = { id: 'us-east-1', kind: 'region', label: 'us-east-1' }

describe('nextFreeSubnet', () => {
  it('takes the first /24 no subnet overlaps', () => {
    expect(nextFreeSubnet('10.0.0.0/16', [])).toBe('10.0.0.0/24')
    expect(nextFreeSubnet('10.0.0.0/16', ['10.0.0.0/24', '10.0.1.0/24'])).toBe('10.0.2.0/24')
    expect(nextFreeSubnet('10.0.0.0/16', ['10.0.0.0/23'])).toBe('10.0.2.0/24')
    expect(nextFreeSubnet('172.31.0.0/16', ['172.31.0.0/20'])).toBe('172.31.16.0/24')
  })

  it('gives nothing when the VPC is full or unknown', () => {
    expect(nextFreeSubnet('10.0.0.0/24', ['10.0.0.0/24'])).toBe('')
    expect(nextFreeSubnet('10.0.0.0/25', [])).toBe('')
    expect(nextFreeSubnet('', [])).toBe('')
  })
})

describe('createDraft', () => {
  it('suggests a free Name tag', () => {
    expect(suggestName(g, LAB, 'vpc')).toBe('lab-06-vpc-1')
  })

  it('fills a VPC from the lab plan', () => {
    const d = createDraft(op('create-vpc'), region, empty, LAB)
    expect(d).toEqual({ op: op('create-vpc'), params: { name: 'lab-06-vpc-1', cidr: '10.66.0.0/16' }, locked: [], rev: 0 })
  })

  it('locks the VPC and the AZ of a subnet dropped on an AZ', () => {
    const d = createDraft(op('create-subnet'), { id: 'vpc-149d0439/us-east-1b', kind: 'az', label: 'us-east-1b' }, g, LAB)
    expect(d.params).toEqual({ name: 'lab-06-subnet-1', vpcId: 'vpc-149d0439', cidr: '10.0.0.0/24', az: 'us-east-1b' })
    expect(d.locked.sort()).toEqual(['az', 'vpcId'])
  })

  it('picks an AZ without a subnet for a subnet dropped on the VPC', () => {
    const d = createDraft(op('create-subnet'), { id: 'vpc-149d0439', kind: 'vpc', label: 'lab06-vpc' }, g, LAB)
    expect(d.params.az).toBe('us-east-1c')
    expect(d.locked).toEqual(['vpcId'])
  })

  it('puts a NAT in the subnet it was dropped on, with a free Elastic IP when there is one', () => {
    expect(freeElasticIps(g)).toEqual([])
    const d = createDraft(op('create-nat-gateway'), { id: 'subnet-83a1f79a', kind: 'subnet-public', label: 'lab06-public-a' }, g, LAB)
    expect(d.params).toMatchObject({ subnetId: 'subnet-83a1f79a', allocationId: '' })
    expect(d.locked).toEqual(['subnetId'])
    const withEip = { ...g, edges: g.edges.filter((e) => e.kind !== 'attached') }
    expect(createDraft(op('create-nat-gateway'), { id: 'subnet-83a1f79a', kind: 'subnet-public', label: '' }, withEip, LAB).params.allocationId)
      .toBe('eipalloc-2cc57421a05781343')
  })

  it('puts a route table in the VPC it was dropped on', () => {
    expect(vpcOf(g, 'subnet-83a1f79a')).toBe('vpc-149d0439')
    const d = createDraft(op('create-route-table'), { id: 'vpc-149d0439', kind: 'vpc', label: 'lab06-vpc' }, g, LAB)
    expect(d.params).toEqual({ name: 'lab-06-route-table-1', vpcId: 'vpc-149d0439' })
  })
})

describe('fixedDraft', () => {
  it('locks every id but leaves a route destination editable', () => {
    const d = fixedDraft(op('create-route'), { routeTableId: 'rtb-1', targetId: 'igw-1', destination: '0.0.0.0/0' })
    expect(d.locked).toEqual(['routeTableId', 'targetId'])
  })
})

describe('EC2 drafts', () => {
  const vpc = { id: 'vpc-149d0439', kind: 'vpc', label: 'lab06-vpc' }
  const subnet = { id: 'subnet-83a1f79a', kind: 'subnet-public', label: 'lab06-public-a' }

  it('puts a security group in the VPC it was dropped on', () => {
    const d = createDraft(op('create-security-group'), vpc, g, LAB07)
    expect(d.params).toEqual({ name: 'lab-07-security-group-1', vpcId: 'vpc-149d0439', description: 'Lab web server' })
    expect(d.locked).toEqual(['vpcId'])
  })

  it('asks only for the name of a key pair', () => {
    expect(createDraft(op('create-key-pair'), region, g, LAB07).params).toEqual({ name: 'lab-07-key-pair-1' })
  })

  it('launches an instance with the lab image, the learner’s own group, the key pair and the lab UserData', () => {
    const d = createDraft(op('run-instances'), subnet, g, LAB07)
    expect(d.params).toEqual({
      name: 'lab-07-instance-1', subnetId: 'subnet-83a1f79a', imageId: 'ami-amazonlinux2023-arm64', instanceType: 't4g.micro',
      securityGroupId: 'sg-dbd2e6007fa2e7eef', keyName: 'lab07-key', userData: LAB07.userData,
    })
    expect(d.locked).toEqual(['subnetId'])
    expect(groupsIn(g, 'vpc-149d0439').map((n) => n.id)).toEqual(['sg-dbd2e6007fa2e7eef', 'sg-b58b05ddff613fe13'])
  })

  it('leaves the group and key empty when there are none yet', () => {
    const d = createDraft(op('run-instances'), subnet, { ...g, nodes: g.nodes.filter((n) => n.kind !== 'security-group' && n.kind !== 'key-pair') }, LAB07)
    expect(d.params).toMatchObject({ securityGroupId: '', keyName: '' })
  })

  it('suggests the web rule for a new inbound rule and locks only the group', () => {
    const d = ingressDraft(op('authorize-security-group-ingress'), 'sg-1')
    expect(d.params).toEqual({ groupId: 'sg-1', protocol: 'tcp', port: '80', cidr: '0.0.0.0/0' })
    expect(d.locked).toEqual(['groupId'])
  })
})
