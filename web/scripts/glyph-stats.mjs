// Prints a markdown table of triangle counts for every manifest icon at several curveSegments values,
// plus any extra candidate SVGs given on the command line (e.g. alternatives inside aws-icon-pkg/).
// Usage: node scripts/glyph-stats.mjs [candidate.svg ...]
import { readFileSync } from 'node:fs'
import { basename, resolve } from 'node:path'
import { JSDOM } from 'jsdom'

globalThis.DOMParser = new JSDOM('').window.DOMParser
const { MANIFEST } = await import('../src/scene/aws-objects/manifest.ts')
const { svgToGeometry, triangleCount, GLYPH_TRIANGLE_BUDGET } = await import('../src/scene/aws-objects/svg-to-geometry.ts')

const SEGMENTS = [2, 3, 4, 6]
const iconDir = resolve(import.meta.dirname, '../src/scene/aws-objects/icons')
const rows = [
  ...MANIFEST.filter((e) => e.file).map((e) => ({ name: e.kind, file: resolve(iconDir, e.file), chosen: e.curveSegments ?? 4 })),
  ...process.argv.slice(2).map((f) => ({ name: `ứng viên: ${basename(f)}`, file: resolve(f), chosen: null })),
]

console.log(`| Loại | File | Kích thước path | ${SEGMENTS.map((s) => `curveSegments ${s}`).join(' | ')} | Đang dùng |`)
console.log(`|---|---|---|${SEGMENTS.map(() => '---').join('|')}|---|`)
for (const r of rows) {
  const svg = readFileSync(r.file, 'utf8')
  const counts = SEGMENTS.map((s) => triangleCount(svgToGeometry(svg, { curveSegments: s })))
  const cells = counts.map((c) => (c > GLYPH_TRIANGLE_BUDGET ? `**${c}**` : String(c)))
  const pathBytes = [...svg.matchAll(/ d="([^"]*)"/g)].reduce((a, m) => a + m[1].length, 0)
  console.log(`| ${r.name} | \`${basename(r.file)}\` | ${(pathBytes / 1024).toFixed(1)} KB | ${cells.join(' | ')} | ${r.chosen ?? '—'} |`)
}
