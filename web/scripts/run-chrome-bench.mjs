// Runs the benchmark suite in real Google Chrome, headed so the GPU is used.
// Usage: node scripts/run-chrome-bench.mjs [start-index]   (dev server on :5174; results land in BENCH_RESULTS_DIR)
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5174/'
const start = Number(process.argv[2] ?? 0)
const { SUITE } = await import('../src/bench/bench.ts')

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, deviceScaleFactor: 2 })
page.on('pageerror', (e) => console.error('[pageerror]', e.message))
await page.goto(`${BASE}?${SUITE[start]}&suite=1&i=${start}`)
await page.waitForFunction(() => document.title === 'SUITE DONE', null, { timeout: 15 * 60_000, polling: 1000 })
console.log('suite done')
await browser.close()
