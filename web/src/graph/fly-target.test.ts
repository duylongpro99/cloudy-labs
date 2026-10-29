import { describe, expect, it } from 'vitest'
import { actionKinds, flyLabel, flyTarget } from './fly-target'
import { graphToScene } from './graph-to-scene'
import type { GraphNode, ResourceGraph } from './types'

const region: GraphNode = { id: 'us-east-1', kind: 'region', label: 'us-east-1', props: {} }
const vpc = (id: string, props: Record<string, unknown> = {}): GraphNode => ({ id, kind: 'vpc', label: id, props })
const scene = (...nodes: GraphNode[]) => {
  const g: ResourceGraph = {
    version: 1,
    takenAt: '',
    emulator: 'floci',
    status: 'ok',
    nodes: [region, ...nodes],
    contains: nodes.map((n) => ({ parent: region.id, child: n.id })),
    edges: [],
    warnings: [],
  }
  return graphToScene(g)
}

describe('flyTarget', () => {
  it('maps actions to the kinds they touch', () => {
    expect(actionKinds('CreateVpc')).toEqual(['vpc'])
    expect(actionKinds('RunInstances')).toEqual(['instance'])
    expect(actionKinds('AssociateRouteTable')).toEqual(['route-table'])
    expect(actionKinds('AuthorizeSecurityGroupIngress')).toEqual(['security-group'])
    expect(actionKinds('DescribeRegions')).toEqual([])
  })

  it('flies to the VPC the next graph added', () => {
    expect(flyTarget('CreateVpc', scene(vpc('vpc-a')), scene(vpc('vpc-a'), vpc('vpc-b')))).toBe('vpc-b')
  })

  it('flies to a node of the kind whose props changed', () => {
    expect(flyTarget('ModifyVpcAttribute', scene(vpc('vpc-a'), vpc('vpc-b')), scene(vpc('vpc-a'), vpc('vpc-b', { dns: true })))).toBe('vpc-b')
  })

  it('flies to a removed node, which is still shrinking away', () => {
    expect(flyTarget('DeleteVpc', scene(vpc('vpc-a'), vpc('vpc-b')), scene(vpc('vpc-a')))).toBe('vpc-b')
  })

  it('falls back to the region when nothing of the kind changed', () => {
    expect(flyTarget('CreateVpc', scene(vpc('vpc-a')), scene(vpc('vpc-a')))).toBeNull()
    expect(flyTarget('PutObject', scene(), scene(vpc('vpc-a')))).toBeNull()
  })

  it('shortens long action names', () => {
    expect(flyLabel('CreateVpc')).toBe('CreateVpc')
    expect(flyLabel('AuthorizeSecurityGroupIngress')).toHaveLength(22)
  })
})
