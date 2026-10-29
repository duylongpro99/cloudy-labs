import { describe, expect, it } from 'vitest'
import { buildFixture, TOTAL_EDGES, TOTAL_NODES } from '../scene/fixture'
import { graphToScene } from './graph-to-scene'
import { syntheticGraph } from './synthetic-graph'
import { parseGraph } from './types'

describe('syntheticGraph', () => {
  it('is a valid graph that draws as the 200-node benchmark scene', () => {
    const scene = graphToScene(parseGraph(syntheticGraph(42)))
    const fixture = buildFixture(42)
    expect(scene.nodes).toHaveLength(TOTAL_NODES)
    expect(scene.edges).toHaveLength(TOTAL_EDGES)
    expect(scene.nodes).toEqual(fixture.nodes)
    expect(scene.attachments.map((a) => a.id).sort()).toEqual(fixture.attachments.map((a) => a.id).sort())
    expect(scene.edges.every((e) => e.kind === 'route' && e.label === '0.0.0.0/0')).toBe(true)
  })

  it('is the same for the same seed', () => {
    expect(syntheticGraph(7)).toEqual(syntheticGraph(7))
  })
})
