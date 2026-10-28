import { describe, expect, it } from 'vitest'
import { entranceDelays, entranceScale, STAGGER_MS } from './entrance'

describe('entranceDelays', () => {
  it('staggers every id on first show', () => {
    expect(entranceDelays(['a', 'b', 'c'], new Set())).toEqual([0, STAGGER_MS, 2 * STAGGER_MS])
  })

  it('keeps shown ids still and staggers only the new ones from zero', () => {
    expect(entranceDelays(['a', 'x', 'b', 'y'], new Set(['a', 'b']))).toEqual([null, 0, null, STAGGER_MS])
  })
})

describe('entranceScale', () => {
  it('starts near zero, ends at one and overshoots in between', () => {
    expect(entranceScale(0)).toBeLessThan(0.01)
    expect(entranceScale(1)).toBe(1)
    expect(Math.max(...[0.6, 0.7, 0.8, 0.9].map(entranceScale))).toBeGreaterThan(1)
  })
})
