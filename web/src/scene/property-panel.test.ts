import { describe, expect, it } from 'vitest'
import { ruleText } from './property-panel'

describe('ruleText', () => {
  it('reads ports, all traffic, and a protocol the collector sends without ports', () => {
    expect(ruleText({ protocol: 'tcp', from: 80, to: 80, sources: ['0.0.0.0/0'] })).toBe('tcp 80 ← 0.0.0.0/0')
    expect(ruleText({ protocol: 'tcp', from: 1024, to: 2048, sources: ['10.0.0.0/8'] })).toBe('tcp 1024-2048 ← 10.0.0.0/8')
    expect(ruleText({ protocol: '-1', from: null, to: null, sources: ['10.0.0.0/8'] })).toBe('mọi giao thức ← 10.0.0.0/8')
    expect(ruleText({ protocol: '50', from: null, to: null, sources: ['10.0.0.0/8'] })).toBe('50 ← 10.0.0.0/8')
  })
})
