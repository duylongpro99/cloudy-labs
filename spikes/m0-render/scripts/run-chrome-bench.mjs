// Runs the benchmark suite (or one screenshot pass) in real Google Chrome, headed so the GPU is used.
// Usage: node scripts/run-chrome-bench.mjs [suite [start-index]|screenshots]   (Vite dev server must be on :5173)
import { chromium } from 'playwright-core'

const BASE = 'http://localhost:5173/'
const what = process.argv[2] ?? 'suite'

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, deviceScaleFactor: 2 })
page.on('console', (m) => m.type() === 'error' && console.error('[page]', m.text()))
page.on('pageerror', (e) => console.error('[pageerror]', e.message))

if (what === 'screenshots') {
  for (const theme of ['light', 'dark']) {
    // A short idle run: the scene renders, settles, and the shot is taken on the static frame.
    await page.goto(`${BASE}?mode=idle&post=full&theme=${theme}&dpr=2&duration=500&warmup=3000`)
    await page.waitForFunction(() => window.__benchResult, null, { timeout: 60_000 })
    await page.locator('#stage').screenshot({ path: `results/screenshot-${theme}-full-dpr2.png` })
    console.log(`screenshot ${theme} saved`)
    // Close-up: node labels (billboard, shown above LABEL_MIN_ZOOM) and Vietnamese diacritics.
    await page.goto(`${BASE}?mode=idle&post=full&theme=${theme}&dpr=2&duration=500&warmup=3000&zoom=40`)
    await page.waitForFunction(() => window.__benchResult, null, { timeout: 60_000 })
    await page.locator('#stage').screenshot({ path: `results/screenshot-${theme}-full-dpr2-zoom40.png` })
  }
} else {
  const start = Number(process.argv[3] ?? 0)
  const { SUITE } = await import('../src/bench.ts').catch(() => ({ SUITE: null }))
  const first = SUITE?.[start] ?? 'mode=bench&post=full&theme=light&dpr=1&run=1'
  await page.goto(`${BASE}?${first}&suite=1&i=${start}`)
  await page.waitForFunction(() => document.title === 'SUITE DONE', null, { timeout: 15 * 60_000, polling: 1000 })
  console.log('suite done')
}
await browser.close()
