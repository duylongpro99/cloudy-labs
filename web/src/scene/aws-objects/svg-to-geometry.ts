// Turns a single-colour icon SVG into an extruded glyph lying flat on the XZ plane:
// largest side 1, centred on the origin, base at y = 0, top at y = depth, facing +Y.
// The SVG's top edge ends up at -Z, matching how flat tray labels read under the isometric camera.
import { BufferGeometry, ExtrudeGeometry, Matrix4 } from 'three'
import { SVGLoader } from 'three/addons/loaders/SVGLoader.js'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'

export interface GlyphOptions {
  depth?: number // relative to the glyph's largest side
  curveSegments?: number
}

export const GLYPH_DEFAULTS = { depth: 0.12, curveSegments: 4 } as const
export const GLYPH_TRIANGLE_BUDGET = 2000

export function triangleCount(g: BufferGeometry): number {
  return (g.index ? g.index.count : g.getAttribute('position').count) / 3
}

// Group icons draw their coloured backdrop as a <rect>; the plinth replaces it, so only the glyph is kept.
function isGlyphPath(path: { userData?: { node?: Element; style?: { fill?: string } } }): boolean {
  const fill = path.userData?.style?.fill
  return path.userData?.node?.nodeName !== 'rect' && !!fill && fill !== 'none' && fill !== 'transparent'
}

// A mirror transform turns outward-facing triangles inward; swap two corners of each triangle to undo it.
function flipWinding(g: BufferGeometry) {
  for (const name of Object.keys(g.attributes)) {
    const a = g.getAttribute(name)
    for (let t = 0; t < a.count; t += 3) {
      for (let c = 0; c < a.itemSize; c++) {
        const v1 = a.getComponent(t + 1, c)
        a.setComponent(t + 1, c, a.getComponent(t + 2, c))
        a.setComponent(t + 2, c, v1)
      }
    }
    a.needsUpdate = true
  }
}

export function svgToGeometry(svgText: string, opts: GlyphOptions = {}): BufferGeometry {
  const depth = opts.depth ?? GLYPH_DEFAULTS.depth
  const curveSegments = opts.curveSegments ?? GLYPH_DEFAULTS.curveSegments
  const data = new SVGLoader().parse(svgText)

  const parts: BufferGeometry[] = []
  for (const path of data.paths) {
    if (!isGlyphPath(path)) continue
    // toShapes reads the fill-rule the loader stored on the path, so evenodd holes stay open.
    for (const shape of path.toShapes()) {
      const g = new ExtrudeGeometry(shape, { depth: 1, bevelEnabled: false, curveSegments })
      g.deleteAttribute('uv') // plain colour materials; dropping uv lets every part merge cheaply
      parts.push(g)
    }
  }
  if (!parts.length) throw new Error('SVG has no filled glyph path')

  const merged = mergeGeometries(parts, false)
  parts.forEach((p) => p.dispose())
  if (!merged) throw new Error('could not merge glyph parts')

  merged.computeBoundingBox()
  const box = merged.boundingBox!
  const side = Math.max(box.max.x - box.min.x, box.max.y - box.min.y)
  const cx = (box.min.x + box.max.x) / 2
  const cy = (box.min.y + box.max.y) / 2
  // SVG (x, y-down, extrusion) -> world (x, extrusion, z = y): centre, scale, then swap Y and Z.
  // The swap is a mirror, hence the winding flip below.
  const toWorld = new Matrix4()
    .set(1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1)
    .multiply(new Matrix4().makeScale(1 / side, 1 / side, depth))
    .multiply(new Matrix4().makeTranslation(-cx, -cy, 0))
  merged.applyMatrix4(toWorld)
  flipWinding(merged)
  merged.computeBoundingBox()
  merged.computeBoundingSphere()
  return merged
}
