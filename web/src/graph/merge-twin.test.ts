// Contract test: the golden twin written by the server tests merges into the golden graph's scene.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { computeLayout } from '../scene/layout'
import { scenePlacements } from '../scene/object-placements'
import { graphToScene } from './graph-to-scene'
import { mergeTwin, withoutGhosts } from './merge-twin'
import { syntheticGraph, syntheticTwin } from './synthetic-graph'
import { parseGraph, parseTwin, type TwinState } from './types'

const FIXTURES = resolve(import.meta.dirname, '../../../server/tests/fixtures/graph')
const scene = graphToScene(parseGraph(JSON.parse(readFileSync(`${FIXTURES}/lab-06-07.graph.json`, 'utf8'))))
const golden = () => parseTwin(JSON.parse(readFileSync(`${FIXTURES}/lab-06-07.twin.json`, 'utf8')))
const VPC = 'vpc-149d0439'

const twin = (over: Partial<TwinState>): TwinState => ({ lab: 'fixture-lab-06', attempt: 1, checks: [], ghosts: [], bound: {}, ...over })
const parentOf = (s: ReturnType<typeof mergeTwin>['scene'], id: string) => s.nodes.find((n) => n.id === id)?.parent

describe('mergeTwin', () => {
  it('leaves the scene alone without a twin or with an empty one', () => {
    expect(mergeTwin(scene, null, true).scene).toBe(scene)
    expect(mergeTwin(scene, twin({ lab: null, attempt: null }), true).scene).toBe(scene)
  })

  it('nests the golden ghosts under real and ghost parents and marks what is achieved', () => {
    const t = golden()
    const { scene: merged, achieved } = mergeTwin(scene, t, true)
    const ghosts = merged.nodes.filter((n) => n.ghost)
    expect(ghosts.map((n) => n.id)).toEqual(t.ghosts.map((g) => g.id))
    expect(parentOf(merged, 'ghost:public-1')).toBe(`${VPC}/us-east-1a`) // a ghost subnet in a real az
    expect(parentOf(merged, 'ghost:nat')).toBe('ghost:public-1') // a ghost in a ghost
    expect(parentOf(merged, 'ghost:eip')).toBe('us-east-1')
    expect(achieved).toEqual(new Set(Object.values(t.bound)))
    expect(merged.nodes.find((n) => n.id === VPC)?.achieved).toBe(true)
    expect(merged.nodes.filter((n) => !n.ghost)).toHaveLength(scene.nodes.length)
    const layout = computeLayout(merged)
    expect(() => scenePlacements(merged, layout)).not.toThrow()
    expect(layout.groups.find((g) => g.node.id === 'ghost:public-1')?.node.ghost).toBe(true)
  })

  it('hides every ghost when switched off but keeps the achieved marks', () => {
    const { scene: merged, achieved } = mergeTwin(scene, golden(), false)
    expect(merged.nodes.some((n) => n.ghost)).toBe(false)
    expect(achieved.has(VPC)).toBe(true)
    expect(merged.nodes.find((n) => n.id === VPC)?.achieved).toBe(true)
  })

  it('marks an attached security group or Elastic IP achieved on its badge', () => {
    const sg = 'sg-dbd2e6007fa2e7eef'
    const eip = 'eipalloc-2cc57421a05781343'
    const { scene: merged, achieved } = mergeTwin(scene, twin({ bound: { 'sg-web': sg, eip } }), true)
    expect(achieved).toEqual(new Set([sg, eip]))
    const marked = merged.attachments.filter((a) => a.achieved).map((a) => a.id)
    expect(marked.length).toBeGreaterThanOrEqual(2)
    expect(marked.every((id) => id.startsWith(sg) || id.startsWith(eip))).toBe(true)
    const placed = scenePlacements(merged, computeLayout(merged)).filter((p) => p.achieved).map((p) => p.id)
    expect(placed.sort()).toEqual(marked.sort())
  })

  it('hangs a ghost on the region when its real parent is gone', () => {
    const t = twin({ ghosts: [{ id: 'ghost:sg', kind: 'security-group', label: 'web', parent: 'vpc-deleted', checks: ['c'] }], bound: { vpc: 'vpc-deleted' } })
    const { scene: merged, achieved } = mergeTwin(scene, t, true)
    expect(parentOf(merged, 'ghost:sg')).toBe('us-east-1')
    expect(achieved.size).toBe(0)
    expect(() => computeLayout(merged)).not.toThrow()
  })

  it('places ghosts as objects of their own, flagged so they are drawn faded and never picked', () => {
    const { scene: merged } = mergeTwin(scene, golden(), true)
    const placed = scenePlacements(merged, computeLayout(merged))
    const ghosts = placed.filter((p) => p.ghost).map((p) => p.id).sort()
    // nat, eip, the route tables and the public subnets' tray badges; az ghosts have no object.
    expect(ghosts).toEqual(['ghost:eip', 'ghost:nat', 'ghost:public-1', 'ghost:public-2', 'ghost:rt-private', 'ghost:rt-public'])
    expect(placed.filter((p) => !p.id.startsWith('ghost:')).every((p) => p.ghost === undefined)).toBe(true)
  })

  it('a 20-ghost bench twin fits into the 200-node synthetic scene', () => {
    const graph = syntheticGraph(42)
    const { scene: merged, achieved } = mergeTwin(graphToScene(graph), syntheticTwin(graph, 20), true)
    expect(merged.nodes.filter((n) => n.ghost)).toHaveLength(20)
    expect(achieved.size).toBe(14) // 2 VPCs and 12 subnets
    expect(() => computeLayout(merged)).not.toThrow()
  })

  it('withoutGhosts gives back the real scene', () => {
    const { scene: merged } = mergeTwin(scene, golden(), true)
    expect(withoutGhosts(merged).nodes.map((n) => n.id)).toEqual(scene.nodes.map((n) => n.id))
    expect(withoutGhosts(scene)).toBe(scene)
  })
})
