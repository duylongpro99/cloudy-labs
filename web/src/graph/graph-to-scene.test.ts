// Contract test: the golden graph written by the server tests must draw without errors.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { computeLayout } from '../scene/layout'
import { scenePlacements } from '../scene/object-placements'
import { graphToScene, resourceId } from './graph-to-scene'
import { parseGraph, type ResourceGraph } from './types'

const GOLDEN = resolve(import.meta.dirname, '../../../server/tests/fixtures/graph/lab-06-07.graph.json')
const golden = () => parseGraph(JSON.parse(readFileSync(GOLDEN, 'utf8')))

describe('graphToScene with the lab 6 + 7 golden graph', () => {
  const graph = golden()
  const scene = graphToScene(graph)
  const layout = computeLayout(scene)
  const placements = scenePlacements(scene, layout)
  const parentOf = new Map(scene.nodes.map((n) => [n.id, n.parent]))
  const instance = graph.nodes.find((n) => n.kind === 'instance')!

  it('draws every resource', () => {
    expect(new Set(placements.map((p) => p.id))).toEqual(
      new Set(graph.nodes.filter((n) => n.kind !== 'az').map((n) => n.id)),
    )
  })

  it('puts the instance in the subnet the graph says', () => {
    const subnet = graph.contains.find((c) => c.child === instance.id)!.parent
    expect(parentOf.get(instance.id)).toBe(subnet)
    const leaf = layout.leaves.find((l) => l.node.id === instance.id)!
    const tray = layout.groups.find((g) => g.node.id === subnet)!
    expect(leaf.x).toBeGreaterThan(tray.x)
    expect(leaf.x).toBeLessThan(tray.x + tray.w)
    expect(leaf.z).toBeGreaterThan(tray.z)
    expect(leaf.z).toBeLessThan(tray.z + tray.d)
  })

  it('draws attached security groups and Elastic IPs as badges on their host', () => {
    expect(scene.attachments).toEqual(
      expect.arrayContaining([
        { id: 'sg-dbd2e6007fa2e7eef', kind: 'security-group', host: instance.id },
        { id: 'eipalloc-2cc57421a05781343', kind: 'elastic-ip', host: 'nat-235f142ec41b5d904' },
      ]),
    )
    // The default security groups are attached to nothing, so they stand on their own in their VPC.
    expect(parentOf.get('sg-default-us-east-1')).toBe('vpc-default-us-east-1')
  })

  it('keeps route, association and uses-key edges with their kind', () => {
    const route = scene.edges.filter((e) => e.kind === 'route')
    expect(route.map((e) => e.to)).toEqual(expect.arrayContaining(['igw-34ddd4cd', 'nat-235f142ec41b5d904']))
    expect(route.every((e) => e.label === '0.0.0.0/0')).toBe(true)
    expect(scene.edges.some((e) => e.kind === 'association' && e.to === 'subnet-83a1f79a')).toBe(true)
    expect(scene.edges.some((e) => e.kind === 'uses-key' && e.from === instance.id)).toBe(true)
    expect(scene.edges.some((e) => (e.kind as string) === 'attached')).toBe(false)
  })

  it('keeps every node for the property panel', () => {
    expect(scene.nodesById.get(instance.id)?.props).toEqual(instance.props)
  })
})

describe('graphToScene edge cases', () => {
  const region = { id: 'us-east-1', kind: 'region' as const, label: 'us-east-1', props: {} }
  const base: ResourceGraph = { version: 1, takenAt: '', emulator: 'floci', status: 'ok', nodes: [region], contains: [], edges: [], warnings: [] }

  it('shows the region alone when the emulator is down', () => {
    const g = golden()
    const scene = graphToScene({ ...g, status: 'emulator-down' })
    expect(scene.nodes).toEqual([{ id: 'us-east-1', label: 'us-east-1', kind: 'region', parent: null }])
    expect(scene.edges).toEqual([])
  })

  it('an empty graph is just the region tray', () => {
    const scene = graphToScene(base)
    expect(computeLayout(scene).groups).toHaveLength(1)
  })

  it('gives a security group shared by two instances one badge per instance', () => {
    const vpc = { id: 'vpc-1', kind: 'vpc' as const, label: 'vpc', props: {} }
    const subnet = { id: 'subnet-1', kind: 'subnet-private' as const, label: 's', props: {} }
    const az = { id: 'vpc-1/a', kind: 'az' as const, label: 'a', props: {} }
    const i = (id: string) => ({ id, kind: 'instance' as const, label: id, props: {} })
    const sg = { id: 'sg-1', kind: 'security-group' as const, label: 'web', props: {} }
    const scene = graphToScene({
      ...base,
      nodes: [region, vpc, az, subnet, i('i-1'), i('i-2'), sg],
      contains: [
        { parent: 'us-east-1', child: 'vpc-1' },
        { parent: 'vpc-1', child: 'vpc-1/a' },
        { parent: 'vpc-1/a', child: 'subnet-1' },
        { parent: 'subnet-1', child: 'i-1' },
        { parent: 'subnet-1', child: 'i-2' },
        { parent: 'vpc-1', child: 'sg-1' },
      ],
      edges: [
        { id: 'a2', kind: 'attached', from: 'sg-1', to: 'i-2', label: '' },
        { id: 'a1', kind: 'attached', from: 'sg-1', to: 'i-1', label: '' },
      ],
    })
    expect(scene.attachments.map((a) => a.id)).toEqual(['sg-1', 'sg-1@i-2'])
    expect(scene.attachments.map((a) => resourceId(a.id))).toEqual(['sg-1', 'sg-1'])
    expect(() => scenePlacements(scene, computeLayout(scene))).not.toThrow()
  })
})

describe('parseGraph', () => {
  it('rejects a graph with an unknown kind', () => {
    const g = JSON.parse(readFileSync(GOLDEN, 'utf8'))
    g.nodes[0].kind = 'lambda'
    expect(() => parseGraph(g)).toThrow(/unknown kind lambda/)
  })

  it('rejects something that is not a graph', () => {
    expect(() => parseGraph({ nodes: [] })).toThrow(/contains/)
  })
})
