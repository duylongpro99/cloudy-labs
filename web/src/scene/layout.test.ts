import { describe, expect, it } from 'vitest'
import { buildFixture, type Fixture, type FixtureNode } from './fixture'
import { computeLayout } from './layout'

const node = (id: string, kind: FixtureNode['kind'], parent: string | null): FixtureNode => ({ id, label: id, kind, parent })

const lab: FixtureNode[] = [
  node('us-east-1', 'region', null),
  node('vpc-1', 'vpc', 'us-east-1'),
  node('igw-1', 'igw', 'vpc-1'),
  node('rtb-1', 'route-table', 'vpc-1'),
  node('vpc-1/us-east-1a', 'az', 'vpc-1'),
  node('subnet-b', 'subnet-public', 'vpc-1/us-east-1a'),
  node('subnet-d', 'subnet-private', 'vpc-1/us-east-1a'),
  node('i-2', 'instance', 'subnet-b'),
  node('i-1', 'instance', 'subnet-b'),
  node('key-1', 'key-pair', 'us-east-1'),
]
const fixture = (nodes: FixtureNode[]): Fixture => ({ nodes, edges: [], attachments: [] })
// Relative to the region's corner: the layout is centred on the origin, so growth anywhere shifts absolute positions.
const positions = (f: Fixture) => {
  const l = computeLayout(f)
  const { x, z } = l.bounds
  return Object.fromEntries([
    ...l.groups.map((g) => [g.node.id, [g.x - x, g.z - z, g.w, g.d]]),
    ...l.leaves.map((v) => [v.node.id, [v.x - x, v.z - z]]),
  ])
}

describe('computeLayout', () => {
  it('depends on the state, not on the order nodes arrive in', () => {
    const shuffled = [lab[0], ...lab.slice(1).reverse()]
    expect(positions(fixture(shuffled))).toEqual(positions(fixture(lab)))
  })

  it('a new subnet moves only the subnets ordered after it in its AZ', () => {
    const before = positions(fixture(lab))
    const after = positions(fixture([...lab, node('subnet-c', 'subnet-public', 'vpc-1/us-east-1a')]))
    // subnet-b sorts first, so nothing above it moves; subnet-d comes after subnet-c and shifts back.
    expect(after['subnet-b']).toEqual(before['subnet-b'])
    expect(after['subnet-d'][1] - after['subnet-b'][1]).toBeGreaterThan(before['subnet-d'][1] - before['subnet-b'][1])
    expect(after['subnet-c'][1]).toBeGreaterThan(after['subnet-b'][1])
    expect(after['subnet-c'][1]).toBeLessThan(after['subnet-d'][1])
  })

  it('lays out a region with nothing in it', () => {
    const l = computeLayout(fixture([node('us-east-1', 'region', null)]))
    expect(l.groups).toHaveLength(1)
    expect(l.leaves).toHaveLength(0)
    expect(l.bounds.w).toBeGreaterThan(0)
  })

  it('still lays out the 200-node benchmark fixture', () => {
    const l = computeLayout(buildFixture(42))
    expect(l.groups.length + l.leaves.length).toBe(200)
  })
})
