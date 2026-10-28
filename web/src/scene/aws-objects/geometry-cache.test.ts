import { describe, expect, it } from 'vitest'
import { outlineGeometry, plinthGeometry } from './geometry-cache'
import { MANIFEST } from './manifest'

const drawable = MANIFEST.filter((e) => e.role !== 'outline-only').map((e) => e.kind)

describe('outlineGeometry', () => {
  it.each(drawable)('leaves the shared %s plinth untouched', (kind) => {
    const plinth = plinthGeometry(kind)
    const normals = Float32Array.from(plinth.getAttribute('normal').array)
    const outline = outlineGeometry(kind)
    expect(outline).not.toBe(plinth)
    expect(outline.getAttribute('normal')).not.toBe(plinth.getAttribute('normal'))
    expect(Float32Array.from(plinth.getAttribute('normal').array)).toEqual(normals)
  })

  it('is cached per kind', () => {
    expect(outlineGeometry('instance')).toBe(outlineGeometry('instance'))
  })
})
