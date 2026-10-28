// Browser checks for the object library in real Google Chrome (headed, so the GPU is used).
// Usage: node scripts/check-scene.mjs <out-dir> [gallery|scene|interact ...]   (dev server on :5174)
//   gallery   gallery screenshots in both themes at glyph coverage 0.6 / 0.75 / 0.85, plus a close-up
//   scene     200-node scene screenshots in both themes, overview and zoomed in
//   interact  hover and click known objects and confirm the scene reports exactly those ids
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = 'http://localhost:5174/'
const out = resolve(process.argv[2] ?? 'bench-results')
const what = process.argv.slice(3).length ? process.argv.slice(3) : ['gallery', 'scene', 'interact']
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, deviceScaleFactor: 2 })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))
let failed = false

async function shot(url, ready, file) {
  await page.goto(BASE + url)
  await page.waitForFunction(ready, null, { timeout: 60_000 })
  await page.locator('#stage').screenshot({ path: resolve(out, file) })
  console.log('saved', file)
}

if (what.includes('gallery')) {
  for (const theme of ['light', 'dark']) {
    for (const coverage of [0.6, 0.75, 0.85]) {
      await shot(`?view=gallery&theme=${theme}&coverage=${coverage}`, () => window.__galleryReady, `gallery-${theme}-coverage${coverage * 100}.png`)
    }
    await shot(`?view=gallery&theme=${theme}&zoom=60`, () => window.__galleryReady, `gallery-${theme}-zoom60.png`)
  }
  // The theme toggle re-colours the live scene without a reload.
  await page.goto(`${BASE}?view=gallery&theme=light`)
  await page.waitForFunction(() => window.__galleryReady, null, { timeout: 60_000 })
  await page.click('#toggle-theme')
  await page.waitForFunction(() => window.__galleryReady, null, { timeout: 60_000 })
  await page.locator('#stage').screenshot({ path: resolve(out, 'gallery-toggled-to-dark.png') })
  console.log('saved gallery-toggled-to-dark.png')
}

if (what.includes('scene')) {
  for (const theme of ['light', 'dark']) {
    for (const zoom of ['', '&zoom=40']) {
      const ready = () => window.__benchResult
      await shot(`?mode=idle&post=full&theme=${theme}&dpr=2&duration=500&warmup=3000${zoom}`, ready, `scene-${theme}-full-dpr2${zoom ? '-zoom40' : ''}.png`)
    }
  }
}

if (what.includes('interact')) {
  await page.goto(`${BASE}?mode=view&theme=light`)
  await page.waitForFunction(() => window.__scene?.screenPoint('i-000'), null, { timeout: 60_000 })
  await page.waitForTimeout(2500) // entrance animation and camera framing
  for (const id of ['i-000', 'nat-subnet-0-0-pub', 'igw-1', 'rtb-0', 'key-0']) {
    const p = await page.evaluate((id) => window.__scene.screenPoint(id), id)
    // Aim at the middle of the block's front-top area rather than its base centre.
    await page.mouse.move(p.x, p.y - 8)
    await page.waitForTimeout(150)
    const hovered = await page.evaluate(() => window.__scene.hovered)
    await page.mouse.click(p.x, p.y - 8)
    await page.waitForTimeout(150)
    const selected = await page.evaluate(() => window.__scene.selected)
    const ok = hovered === id && selected === id
    failed ||= !ok
    console.log(`${ok ? 'PASS' : 'FAIL'} ${id}: hovered=${hovered} selected=${selected}`)
  }
  await page.locator('#stage').screenshot({ path: resolve(out, 'scene-selected.png') })
  await page.mouse.move(5, 5)
  await page.waitForTimeout(150)
  const cleared = await page.evaluate(() => window.__scene.hovered)
  failed ||= cleared !== null
  console.log(`${cleared === null ? 'PASS' : 'FAIL'} pointer off the scene clears hover (hovered=${cleared})`)
}

if (errors.length) console.log('page errors:\n' + errors.join('\n'))
await browser.close()
process.exit(failed ? 1 : 0)
