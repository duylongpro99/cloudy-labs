import { describe, expect, it } from 'vitest'
import { ENTRANCE_MS, entranceProgressFor, entranceScale, entranceStarts, EXIT_MS, exitScale, FADE_CURVE, Presence, SCALE_CURVE, STAGGER_MS } from './entrance'

const item = (id: string) => ({ id })

describe('entranceStarts', () => {
  it('staggers every id on first show', () => {
    expect([...entranceStarts(['a', 'b', 'c'], new Map(), 100).values()]).toEqual([100, 100 + STAGGER_MS, 100 + 2 * STAGGER_MS])
  })

  it('keeps the start of ids already present and staggers only the new ones', () => {
    const starts = entranceStarts(['a', 'x', 'b', 'y'], new Map([['a', 5], ['b', 7]]), 100)
    expect(Object.fromEntries(starts)).toEqual({ a: 5, x: 100, b: 7, y: 100 + STAGGER_MS })
  })
})

describe('entranceScale', () => {
  it('starts near zero, ends at one and overshoots in between', () => {
    expect(entranceScale(0)).toBeLessThan(0.01)
    expect(entranceScale(1)).toBe(1)
    expect(Math.max(...[0.6, 0.7, 0.8, 0.9].map(entranceScale))).toBeGreaterThan(1)
  })

  it('can be inverted on its rising part', () => {
    for (const k of [0.1, 0.5, 0.9]) expect(entranceScale(entranceProgressFor(k))).toBeCloseTo(k, 4)
  })

  it('exits from one down to zero', () => {
    expect(exitScale(0)).toBe(1)
    expect(exitScale(0.5)).toBeGreaterThan(0)
    expect(exitScale(1)).toBe(0)
  })
})

describe('Presence', () => {
  it('a placement change half-way through an entrance does not restart it', () => {
    const p = new Presence(SCALE_CURVE)
    p.update([item('a')], 0)
    p.update([item('a'), item('b')], 200) // the list changes while "a" is still growing
    expect(p.get('a', 250)!.value).toBeCloseTo(entranceScale(250 / ENTRANCE_MS), 6)
    expect(p.get('b', 250)!.value).toBeCloseTo(entranceScale(50 / ENTRANCE_MS), 6)
  })

  it('objects already on screen stay at full size', () => {
    const p = new Presence(SCALE_CURVE)
    p.update([item('a')], 0)
    p.update([item('a'), item('b')], 1000)
    expect(p.get('a', 1000)).toEqual({ value: 1, done: true })
    expect(p.get('b', 1000)!.done).toBe(false)
  })

  it('a removed id shrinks away and is dropped after EXIT_MS', () => {
    const p = new Presence(SCALE_CURVE)
    p.update([item('a'), item('b')], 0)
    p.update([item('a')], 1000)
    expect(p.exiting().map((i) => i.id)).toEqual(['b'])
    const mid = p.get('b', 1000 + EXIT_MS / 2)!
    expect(mid.value).toBeGreaterThan(0)
    expect(mid.value).toBeLessThan(1)
    expect(p.prune(1000 + EXIT_MS / 2)).toBe(false)
    expect(p.get('b', 1000 + EXIT_MS)).toEqual({ value: 0, done: true })
    expect(p.prune(1000 + EXIT_MS)).toBe(true)
    expect(p.get('b', 2000)).toBeNull()
    expect(p.exiting()).toEqual([])
  })

  it('an id that comes back while exiting grows again from its current size', () => {
    const p = new Presence(SCALE_CURVE)
    p.update([item('a')], 0)
    p.update([], 1000)
    const before = p.get('a', 1000 + EXIT_MS / 2)!.value
    p.update([item('a')], 1000 + EXIT_MS / 2)
    expect(p.exiting()).toEqual([])
    expect(p.get('a', 1000 + EXIT_MS / 2)!.value).toBeCloseTo(before, 3)
    expect(p.get('a', 1000 + EXIT_MS / 2 + ENTRANCE_MS)!.value).toBe(1)
  })

  it('shows everything at full size when not animating', () => {
    const p = new Presence(SCALE_CURVE)
    p.update([item('a')], 0, false)
    expect(p.get('a', 0)).toEqual({ value: 1, done: true })
  })

  it('fades linearly for trays', () => {
    const p = new Presence(FADE_CURVE)
    p.update([item('vpc')], 0)
    expect(p.get('vpc', EXIT_MS / 2)!.value).toBeCloseTo(0.5)
    p.update([], EXIT_MS)
    expect(p.get('vpc', EXIT_MS * 1.5)!.value).toBeCloseTo(0.5)
  })
})
