// Placeholder service icons drawn as simple SVG (PRD F3.8: self-drawn icons by default).
// One texture per kind and theme, shared by every block of that kind.
import { CanvasTexture, SRGBColorSpace, type Texture } from 'three'
import type { LeafKind } from '../fixture'
import type { ThemeName } from './theme'

const GLYPH: Record<LeafKind, string> = {
  // chip with pins
  instance: '<rect x="18" y="18" width="28" height="28" rx="3"/><path d="M24 12v6M32 12v6M40 12v6M24 46v6M32 46v6M40 46v6M12 24h6M12 32h6M12 40h6M46 24h6M46 32h6M46 40h6"/>',
  // arrows converging through a gate
  nat: '<circle cx="32" cy="32" r="18"/><path d="M14 32h36M38 24l8 8-8 8"/>',
  // globe
  igw: '<circle cx="32" cy="32" r="18"/><path d="M14 32h36M32 14c-8 10-8 26 0 36M32 14c8 10 8 26 0 36"/>',
}

function svg(kind: LeafKind, theme: ThemeName) {
  const stroke = theme === 'dark' ? '#0F141A' : '#FFFFFF'
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="128" height="128">
    <g fill="none" stroke="${stroke}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">${GLYPH[kind]}</g></svg>`
}

const cache = new Map<string, Texture>()

// onReady fires once the SVG has been drawn, so a demand-mode canvas can re-render.
export function iconTexture(kind: LeafKind, theme: ThemeName, onReady?: () => void): Texture {
  const key = `${kind}-${theme}`
  const hit = cache.get(key)
  if (hit) return hit
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const tex = new CanvasTexture(canvas)
  tex.colorSpace = SRGBColorSpace
  const img = new Image()
  img.onload = () => {
    canvas.getContext('2d')!.drawImage(img, 0, 0, 128, 128)
    tex.needsUpdate = true
    onReady?.()
  }
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg(kind, theme))}`
  cache.set(key, tex)
  return tex
}
