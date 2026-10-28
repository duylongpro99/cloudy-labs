// One extruded glyph geometry and one plinth geometry per kind, built on first use and shared by every instance.
// SVGs are bundled as strings, so building needs no network request.
import { CylinderGeometry, type BufferGeometry } from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js'
import type { AwsKind } from './manifest'
import { MANIFEST_BY_KIND } from './manifest'
import { plinthShape } from './object-specs'
import { svgToGeometry } from './svg-to-geometry'

const SVG_TEXT = import.meta.glob('./icons/*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

export function iconSvg(kind: AwsKind): string {
  const file = MANIFEST_BY_KIND[kind].file
  if (!file) throw new Error(`kind ${kind} has no icon`)
  const text = SVG_TEXT[`./icons/${file}`]
  if (!text) throw new Error(`icon ${file} for kind ${kind} is not bundled; run scripts/import-aws-icons.mjs`)
  return text
}

const cache = new Map<AwsKind, BufferGeometry>()

export function glyphGeometry(kind: AwsKind): BufferGeometry {
  let g = cache.get(kind)
  if (!g) {
    g = svgToGeometry(iconSvg(kind), { curveSegments: MANIFEST_BY_KIND[kind].curveSegments })
    cache.set(kind, g)
  }
  return g
}

const plinths = new Map<AwsKind, BufferGeometry>()

// The plinth under the glyph: a rounded box (blocks, tray badges) or a puck (attach badges), base at y = 0.
export function plinthGeometry(kind: AwsKind): BufferGeometry {
  let g = plinths.get(kind)
  if (!g) {
    const p = plinthShape(kind)
    g = p.shape === 'box' ? new RoundedBoxGeometry(p.side, p.height, p.side, 2, p.radius) : new CylinderGeometry(p.side / 2, p.side / 2, p.height, 32)
    g.translate(0, p.height / 2, 0)
    plinths.set(kind, g)
  }
  return g
}

const outlines = new Map<AwsKind, BufferGeometry>()

// A separate copy of the plinth for drei <Outlines>. Outlines with a non-zero angle rewrites the normals
// of a non-indexed geometry in place and disposes it on unmount, which would corrupt the shared plinth.
// Creasing is done here once, and Outlines is given angle={0} so it uses this copy as-is.
export function outlineGeometry(kind: AwsKind): BufferGeometry {
  let g = outlines.get(kind)
  if (!g) {
    g = toCreasedNormals(plinthGeometry(kind).clone(), Math.PI)
    outlines.set(kind, g)
  }
  return g
}
