import { describe, expect, it } from 'vitest'
import type { EdgeAnchor } from '../scene/object-placements'
import type { ReachHop } from './reachability-api'
import { PATH_RISE, pathPoints } from './reachability-layer'

const hop = (id: string, verdict: ReachHop['verdict'] = 'allow'): ReachHop => ({ resource_id: id, kind: 'x', verdict, reason: 'allowed', rule: null })
const ANCHORS = new Map<string, EdgeAnchor>([
  ['i-web', { at: [0, 1, 0], kind: 'instance' }],
  ['rtb-a', { at: [4, 0.5, 2], kind: 'route-table' }],
  ['i-app', { at: [8, 1, 0], kind: 'instance' }],
])

describe('pathPoints', () => {
  it('keeps the hops that are objects in the scene, numbered as in the panel', () => {
    const points = pathPoints([hop('internet', 'forward'), hop('i-web'), hop('sg-web'), hop('rtb-a', 'forward'), hop('i-app')], ANCHORS)
    expect(points.map((p) => [p.id, p.n])).toEqual([['i-web', 2], ['rtb-a', 4], ['i-app', 5]])
    expect(points[0].at).toEqual([0, 1 + PATH_RISE, 0])
  })

  it('marks the blocking hop, merged into a repeat of the same object', () => {
    const points = pathPoints([hop('i-web'), hop('rtb-a', 'forward'), hop('rtb-a', 'deny')], ANCHORS)
    expect(points.map((p) => [p.id, p.blocked])).toEqual([['i-web', false], ['rtb-a', true]])
  })

  it('is empty when no hop is in the scene', () => {
    expect(pathPoints([hop('internet', 'forward'), hop('sg-x', 'deny')], ANCHORS)).toEqual([])
  })
})
