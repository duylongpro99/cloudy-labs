// Counts frames rendered while the scene should be idle, for several URL variants.
// Usage: node scripts/idle-probe.mjs "post=full" "post=flat" ...   (Vite dev server on :5173)
import { chromium } from 'playwright-core'

const b = await chromium.launch({ channel: 'chrome', headless: false })
const p = await b.newPage({ viewport: { width: 1300, height: 960 } })
for (const q of process.argv.slice(2)) {
  await p.goto(`http://localhost:5173/?mode=idle&duration=4000&warmup=3000&run=0&${q}`)
  await p.waitForFunction(() => window.__benchResult, null, { timeout: 60_000 })
  console.log(q, '->', await p.evaluate(() => window.__benchResult.idleFramesRendered), 'frames in 4 s')
}
await b.close()
