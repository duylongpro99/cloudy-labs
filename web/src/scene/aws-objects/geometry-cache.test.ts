import { describe, expect, it } from 'vitest'
import { outlineGeometry, plinthGeometry } from './geometry-cache'
import { kindView, registryData } from '../../registry/registry'

// Every drawable registry kind plus one no registry lists, which must draw as the fallback object.
const drawable = [...registryData().kinds.filter((k) => k.role !== 'outline-only').map((k) => k.kind), 'not-a-registry-kind']

describe('outlineGeometry', () => {
  it.each(drawable)('leaves the shared %s plinth untouched', (kind) => {
    const plinth = plinthGeometry(kind)
    const normals = Float32Array.from(plinth.getAttribute('normal').array)
    const outline = outlineGeometry(kind)
    expect(outline).not.toBe(plinth)
    expect(outline.getAttribute('normal')).not.toBe(plinth.getAttribute('normal'))
    expect(Float32Array.from(plinth.getAttribute('normal').array)).toEqual(normals)
  })

  it('draws a kind with no bundled icon from the fallback glyph', () => {
    expect(kindView('not-a-registry-kind').fallback).toBe(true)
    expect(outlineGeometry('not-a-registry-kind').getAttribute('position').count).toBeGreaterThan(0)
  })

  it('is cached per kind', () => {
    expect(outlineGeometry('instance')).toBe(outlineGeometry('instance'))
  })
})
