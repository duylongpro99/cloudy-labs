// Physical size of every object, in world units on the M0 layout grid (CELL 2.2, leaf BLOCK 1.4).
// A placement's position is the centre of the object's base; everything grows upward from there.
import type { AwsKind, ObjectRole } from './manifest'
import { MANIFEST_BY_KIND } from './manifest'
import { GLYPH_DEFAULTS } from './svg-to-geometry'

export type Vec3 = [number, number, number]

export const BLOCK_SIDE = 1.4
export const BLOCK_RADIUS = 0.08

// Taller blocks for the resources a learner works with most; small ones for supporting resources.
export const BLOCK_HEIGHT: Partial<Record<AwsKind, number>> = {
  instance: 0.9,
  nat: 0.6,
  igw: 0.6,
  'route-table': 0.4,
  'key-pair': 0.4,
}

export const TRAY_BADGE = { side: 0.9, height: 0.1, radius: 0.06 }
export const ATTACH_BADGE = { radius: 0.3, height: 0.14 }

// Share of the plinth's top face the glyph spans. 0.6, 0.75 and 0.85 were compared in the gallery.
export const GLYPH_COVERAGE = 0.75

export interface PlinthShape {
  shape: 'box' | 'puck'
  side: number // box width/depth, or puck diameter
  height: number
  radius: number // box corner rounding
}

export function plinthShape(kind: AwsKind): PlinthShape {
  const role: ObjectRole = MANIFEST_BY_KIND[kind].role
  switch (role) {
    case 'block':
      return { shape: 'box', side: BLOCK_SIDE, height: BLOCK_HEIGHT[kind] ?? 0.6, radius: BLOCK_RADIUS }
    case 'tray-badge':
      return { shape: 'box', side: TRAY_BADGE.side, height: TRAY_BADGE.height, radius: TRAY_BADGE.radius }
    case 'attach-badge':
      return { shape: 'puck', side: ATTACH_BADGE.radius * 2, height: ATTACH_BADGE.height, radius: 0 }
    case 'outline-only':
      throw new Error(`kind ${kind} has no object`)
  }
}

// Height of the object's top surface (plinth plus glyph), e.g. where edges and labels attach.
export function objectHeight(kind: AwsKind, coverage = GLYPH_COVERAGE): number {
  const p = plinthShape(kind)
  return p.height + p.side * coverage * GLYPH_DEFAULTS.depth
}

// Tray badge: in the tray's near-left label strip, where the tray label starts.
// The label moves right by TRAY_LABEL_SHIFT to make room for it.
export const TRAY_LABEL_INSET = 0.9
export const TRAY_LABEL_FROM_NEAR_EDGE = 0.6
export const TRAY_LABEL_SHIFT = TRAY_BADGE.side + 0.25

export function trayBadgePosition(tray: { x: number; z: number; d: number }, trayTop: number): Vec3 {
  return [tray.x + TRAY_LABEL_INSET + TRAY_BADGE.side / 2, trayTop, tray.z + tray.d - TRAY_LABEL_FROM_NEAR_EDGE]
}

// Attach badge: on the host's top face, over the corner nearest the isometric camera (+X, +Z);
// a second attachment takes the next visible corner (-X, +Z).
export function attachPosition(host: { position: Vec3; kind: AwsKind }, slot = 0): Vec3 {
  const p = plinthShape(host.kind)
  const inset = p.side / 2 - ATTACH_BADGE.radius * 0.55
  const [x, y, z] = host.position
  return [x + (slot === 0 ? inset : -inset), y + p.height, z + inset]
}
