// One extruded glyph geometry and one plinth geometry per kind, built on first use and shared by every instance.
// SVGs are bundled as strings, so building needs no network request.
import { CylinderGeometry, type BufferGeometry } from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js'
import { kindView } from '../../registry/registry'
import { FALLBACK_ICON, ICON_SVG } from './icons'
import { plinthShape } from './object-specs'
import { svgToGeometry } from './svg-to-geometry'

// kindView gives a kind without bundled artwork the fallback icon, so this always finds one.
export function iconSvg(kind: string): string {
  return ICON_SVG.get(kindView(kind).icon ?? FALLBACK_ICON) ?? ICON_SVG.get(FALLBACK_ICON)!
}

const cache = new Map<string, BufferGeometry>()

export function glyphGeometry(kind: string): BufferGeometry {
  let g = cache.get(kind)
  if (!g) {
    g = svgToGeometry(iconSvg(kind), { curveSegments: kindView(kind).curveSegments ?? undefined })
    cache.set(kind, g)
  }
  return g
}

const plinths = new Map<string, BufferGeometry>()

// The plinth under the glyph: a rounded box (blocks, tray badges) or a puck (attach badges), base at y = 0.
export function plinthGeometry(kind: string): BufferGeometry {
  let g = plinths.get(kind)
  if (!g) {
    const p = plinthShape(kind)
    g = p.shape === 'box' ? new RoundedBoxGeometry(p.side, p.height, p.side, 2, p.radius) : new CylinderGeometry(p.side / 2, p.side / 2, p.height, 32)
    g.translate(0, p.height / 2, 0)
    plinths.set(kind, g)
  }
  return g
}

const outlines = new Map<string, BufferGeometry>()

// A separate copy of the plinth for drei <Outlines>. Outlines with a non-zero angle rewrites the normals
// of a non-indexed geometry in place and disposes it on unmount, which would corrupt the shared plinth.
// Creasing is done here once, and Outlines is given angle={0} so it uses this copy as-is.
export function outlineGeometry(kind: string): BufferGeometry {
  let g = outlines.get(kind)
  if (!g) {
    g = toCreasedNormals(plinthGeometry(kind).clone(), Math.PI)
    outlines.set(kind, g)
  }
  return g
}
