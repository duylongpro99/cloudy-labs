// Prints a markdown table of every benchmark run in a results directory, and the idle checks.
// Usage: node scripts/summarize-bench.mjs [results-dir]
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const THRESHOLD_MS = 20 // 50 fps
const dir = resolve(process.argv[2] ?? 'bench-results')
const runs = readdirSync(dir)
  .filter((f) => f.endsWith('.json'))
  .map((f) => JSON.parse(readFileSync(resolve(dir, f), 'utf8')))
const order = { full: 0, lite: 1, flat: 2 }
const bench = runs
  .filter((r) => r.mode === 'bench')
  .sort((a, b) => a.browser.localeCompare(b.browser) || order[a.post] - order[b.post] || a.theme.localeCompare(b.theme) || a.dpr - b.dpr)

console.log('| Trình duyệt | Hậu kỳ | Chủ đề | DPR | p50 ms | p95 ms | p99 ms | max ms | FPS TB | Draw call | Triangle | Program | p95 ≤ 20 ms |')
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for (const r of bench) {
  const f = r.frameTimeMs
  console.log(`| ${r.browser} | ${r.post} | ${r.theme} | ${r.dpr} | ${f.p50} | ${f.p95} | ${f.p99} | ${f.max} | ${r.avgFps} | ${r.drawCalls.p50} | ${r.triangles.p50} | ${r.programs} | ${f.p95 <= THRESHOLD_MS ? 'đạt' : '**không đạt**'} |`)
}
console.log('\n| Trình duyệt | Idle: khung hình được render trong cửa sổ đo |')
console.log('|---|---|')
for (const r of runs.filter((r) => r.mode === 'idle')) console.log(`| ${r.browser} | ${r.idleFramesRendered} trong ${r.idleWindowMs / 1000} s |`)
const gpus = [...new Set(runs.filter((r) => r.gpu).map((r) => `${r.browser}: ${r.gpu}`))]
console.log(`\nGPU báo cáo: ${gpus.join('; ')}`)
