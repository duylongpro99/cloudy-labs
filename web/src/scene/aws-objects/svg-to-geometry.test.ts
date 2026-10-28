import { Raycaster, Mesh, Vector3, type BufferGeometry } from 'three'
import { describe, expect, it } from 'vitest'
import { iconSvg } from './geometry-cache'
import { MANIFEST } from './manifest'
import { GLYPH_DEFAULTS, GLYPH_TRIANGLE_BUDGET, svgToGeometry, triangleCount } from './svg-to-geometry'

const withIcons = MANIFEST.filter((e) => e.file)

// True when a ray dropped straight down at (x, z) hits the glyph.
function solidAt(g: BufferGeometry, x: number, z: number) {
  const ray = new Raycaster(new Vector3(x, 5, z), new Vector3(0, -1, 0))
  return ray.intersectObject(new Mesh(g)).length > 0
}

describe('svgToGeometry', () => {
  it.each(withIcons.map((e) => [e.kind, e] as const))('%s: normalised, flat, within budget', (_, e) => {
    const g = svgToGeometry(iconSvg(e.kind), { curveSegments: e.curveSegments })
    const { min, max } = g.boundingBox!
    expect(Math.max(max.x - min.x, max.z - min.z)).toBeCloseTo(1, 3)
    expect(min.y).toBeCloseTo(0, 6)
    expect(max.y).toBeCloseTo(GLYPH_DEFAULTS.depth, 6)
    expect((min.x + max.x) / 2).toBeCloseTo(0, 6)
    expect((min.z + max.z) / 2).toBeCloseTo(0, 6)
    expect(triangleCount(g)).toBeGreaterThan(0)
    expect(triangleCount(g)).toBeLessThanOrEqual(GLYPH_TRIANGLE_BUDGET)
  })

  it.each(withIcons.map((e) => [e.kind, e] as const))('%s: triangles face outward and caps face up/down', (_, e) => {
    const g = svgToGeometry(iconSvg(e.kind), { curveSegments: e.curveSegments })
    const pos = g.getAttribute('position')
    const nrm = g.getAttribute('normal')
    const [a, b, c, n, ab, ac] = Array.from({ length: 6 }, () => new Vector3())
    let wrong = 0
    let caps = 0
    for (let t = 0; t < pos.count; t += 3) {
      a.fromBufferAttribute(pos, t)
      b.fromBufferAttribute(pos, t + 1)
      c.fromBufferAttribute(pos, t + 2)
      const face = ab.subVectors(b, a).cross(ac.subVectors(c, a))
      if (face.lengthSq() < 1e-14) continue // degenerate sliver
      n.fromBufferAttribute(nrm, t)
      if (face.dot(n) <= 0) wrong++
      // Cap triangles: all three corners at the same height.
      if (Math.abs(a.y - b.y) < 1e-9 && Math.abs(a.y - c.y) < 1e-9) {
        caps++
        expect(Math.sign(face.y), `cap at y=${a.y}`).toBe(a.y > GLYPH_DEFAULTS.depth / 2 ? 1 : -1)
      }
    }
    expect(wrong).toBe(0)
    expect(caps).toBeGreaterThan(0)
  })

  it('keeps evenodd holes open', () => {
    const ring = `<svg viewBox="0 0 48 48"><g fill-rule="evenodd"><path fill="#000" d="M4,4 L44,4 L44,44 L4,44 Z M10,10 L38,10 L38,38 L10,38 Z"/></g></svg>`
    const g = svgToGeometry(ring)
    expect(solidAt(g, 0, 0)).toBe(false)
    expect(solidAt(g, 0.45, 0)).toBe(true)
  })

  it('keeps the EC2 chip hollow and its frame solid', () => {
    const g = svgToGeometry(iconSvg('instance'))
    expect(solidAt(g, 0, 0)).toBe(false)
    // Frame: SVG x = 8 on a glyph spanning 2..46 maps to (8 - 24) / 44.
    expect(solidAt(g, (8 - 24) / 44, 0)).toBe(true)
  })

  it('keeps the SVG top edge at -Z (not mirrored)', () => {
    // A bar along the top edge only.
    const bar = `<svg viewBox="0 0 48 48"><path fill="#000" d="M4,4 L44,4 L44,8 L4,8 Z M4,40 L8,40 L8,44 L4,44 Z"/></svg>`
    const g = svgToGeometry(bar)
    expect(solidAt(g, 0, -0.45)).toBe(true)
    expect(solidAt(g, 0, 0.45)).toBe(false)
    // The small square sits bottom-left: -X, +Z.
    expect(solidAt(g, -0.47, 0.47)).toBe(true)
  })

  it('drops the coloured backdrop of group icons', () => {
    const g = svgToGeometry(iconSvg('region'))
    const { min, max } = g.boundingBox!
    // The backdrop is a full 40x40 square; the glyph alone has empty corners.
    expect(Math.max(max.x - min.x, max.z - min.z)).toBeCloseTo(1, 3)
    // A kept backdrop would make the glyph square and solid in every corner.
    expect(max.x - min.x).not.toBeCloseTo(max.z - min.z, 2)
    expect([solidAt(g, min.x + 0.01, min.z + 0.01), solidAt(g, max.x - 0.01, max.z - 0.01)]).not.toEqual([true, true])
  })
})
