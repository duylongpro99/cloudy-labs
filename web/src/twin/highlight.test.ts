// What a selected check lights up, over the golden graph and twin the server tests write.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { graphToScene } from '../graph/graph-to-scene'
import { mergeTwin } from '../graph/merge-twin'
import { parseGraph, parseTwin, type TwinState } from '../graph/types'
import { withContainers } from '../scene/check-highlight'
import { highlightFor } from './highlight'
import { selectedCheck } from './use-check-selection'

const FIXTURES = resolve(import.meta.dirname, '../../../server/tests/fixtures/graph')
const real = graphToScene(parseGraph(JSON.parse(readFileSync(`${FIXTURES}/lab-06-07.graph.json`, 'utf8'))))
const twin = parseTwin(JSON.parse(readFileSync(`${FIXTURES}/lab-06-07.twin.json`, 'utf8')))
const scene = mergeTwin(real, twin, true).scene

describe('highlightFor', () => {
  it('lights up the resources a passed check reported and the ghosts that wait on it', () => {
    const ids = highlightFor('subnets-two-azs', twin, scene)
    expect([...ids].sort()).toEqual(['ghost:public-1', 'ghost:public-2', 'subnet-44acdeb7', 'subnet-83a1f79a', 'subnet-b893d7ba', 'subnet-e917cc42'])
  })

  it('lights up only ghosts for a check that has not passed', () => {
    expect([...highlightFor('nat-in-public-subnet', twin, scene)].sort()).toEqual(['ghost:eip', 'ghost:nat'])
  })

  it('finds a reported security group or Elastic IP through its badge id', () => {
    const t: TwinState = {
      ...twin,
      checks: [{ id: 'sg', task: 'security-group', description: '', status: 'passed', message: '', resourceIds: ['sg-dbd2e6007fa2e7eef', 'eipalloc-2cc57421a05781343'] }],
      ghosts: [],
    }
    const badges = scene.attachments.filter((a) => a.id.startsWith('sg-dbd2') || a.id.startsWith('eipalloc-')).map((a) => a.id)
    expect(badges.length).toBe(2)
    expect([...highlightFor('sg', t, scene)].sort()).toEqual(badges.sort())
  })

  it('leaves hidden ghosts out, so a check that reported nothing dims nothing', () => {
    expect(highlightFor('nat-in-public-subnet', twin, mergeTwin(real, twin, false).scene).size).toBe(0)
  })

  it('is empty for an unknown check or no twin', () => {
    expect(highlightFor('nope', twin, scene).size).toBe(0)
    expect(highlightFor('vpc-exists', null, scene).size).toBe(0)
  })

  it('keeps the trays that hold a lit object, so only the others are dimmed', () => {
    const kept = withContainers(highlightFor('nat-in-public-subnet', twin, scene), scene)
    // ghost NAT -> ghost public subnet -> real az -> VPC -> region; the ghost EIP sits in the region.
    expect(kept).toEqual(new Set(['ghost:nat', 'ghost:eip', 'ghost:public-1', 'vpc-149d0439/us-east-1a', 'vpc-149d0439', 'us-east-1']))
  })
})

describe('selectedCheck', () => {
  const pick = { id: 'vpc-exists', attempt: 'fixture-lab-06#3' }

  it('keeps a selection for the attempt it was made in', () => {
    expect(selectedCheck(pick, twin)).toBe('vpc-exists')
  })

  it('drops it after a reset, in another lab, or once the check is gone', () => {
    expect(selectedCheck(pick, { ...twin, attempt: 4 })).toBeNull()
    expect(selectedCheck(pick, { ...twin, lab: 'fixture-lab-07' })).toBeNull()
    expect(selectedCheck(pick, { ...twin, checks: twin.checks.filter((c) => c.id !== 'vpc-exists') })).toBeNull()
    expect(selectedCheck(pick, null)).toBeNull()
  })
})
