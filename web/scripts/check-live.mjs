// Browser checks for the live scene in real Google Chrome, with the lab-server faked:
// the page's /ws is intercepted and the script sends graphs and API events itself.
// Usage: node scripts/check-live.mjs [out-dir]   (dev server on :5174; no lab-server needed)
// Graphs come from the lab 6 + 7 golden file the server tests write.
import { mkdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5174/'
const out = resolve(process.argv[2] ?? '../plans/261029-1006-m2-resource-graph-collector-scene/notes')
mkdirSync(out, { recursive: true })

const golden = JSON.parse(readFileSync(new URL('../../server/tests/fixtures/graph/lab-06-07.graph.json', import.meta.url), 'utf8'))
const instance = golden.nodes.find((n) => n.kind === 'instance')
const subnet = golden.contains.find((c) => c.child === instance.id).parent
const others = golden.nodes.filter((n) => n.kind !== 'az' && n.id !== instance.id).map((n) => n.id)

const without = (g, id) => ({
  ...g,
  nodes: g.nodes.filter((n) => n.id !== id),
  contains: g.contains.filter((c) => c.child !== id && c.parent !== id),
  edges: g.edges.filter((e) => e.from !== id && e.to !== id),
})
const withExtra = (g, id) => ({
  ...g,
  nodes: [...g.nodes, { ...instance, id, label: id }],
  contains: [...g.contains, { parent: subnet, child: id }],
})
const A = without(golden, instance.id) // lab state before RunInstances
const B = golden
const C = withExtra(B, 'i-extra')

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, deviceScaleFactor: 2 })
const errors = []
// The app has no favicon; Chrome's request for one is not a page error.
page.on('console', (m) => m.type() === 'error' && !m.location().url.endsWith('/favicon.ico') && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))
let failed = false
const check = (ok, what) => {
  failed ||= !ok
  console.log(`${ok ? 'PASS' : 'FAIL'} ${what}`)
}

let socket = null
await page.routeWebSocket('**/ws', (ws) => void (socket = ws))
let version = 0
const sendGraph = (g) => socket.send(JSON.stringify({ type: 'graph', graph: { ...g, version: ++version } }))
const sendEvent = (action) => socket.send(JSON.stringify({ type: 'api-event', service: 'ec2', action, seq: version, write: true }))
const scale = (id) => page.evaluate((id) => window.__scene.scaleOf(id), id)
const settle = () => page.waitForTimeout(1500)

await page.emulateMedia({ colorScheme: 'light' })
await page.goto(BASE)
// The socket opens before the first graph; the scene mounts once one arrives.
while (!socket) await page.waitForTimeout(50)
sendGraph(A)
await page.waitForFunction(() => window.__scene?.scaleOf, null, { timeout: 30_000 })
await settle()

// 1. Only the new instance animates in.
sendGraph(B)
await page.waitForTimeout(60)
const s1 = await scale(instance.id)
const rest = await page.evaluate((ids) => ids.map((id) => window.__scene.scaleOf(id)), others)
check(s1 !== null && s1 < 1, `new instance is still growing after 60 ms (scale=${s1?.toFixed(3)})`)
check(rest.every((s) => s === 1), `every other object stays at full size (${rest.filter((s) => s !== 1).length} not)`)

// 2. A graph that lands mid-entrance does not restart it.
const before = await scale(instance.id)
sendGraph(C)
await page.waitForTimeout(80)
const after = await scale(instance.id)
check(after >= before, `entrance carries on through a graph change (${before.toFixed(3)} -> ${after.toFixed(3)})`)
await settle()

// 3. A removed instance shrinks away, then leaves the probe.
sendGraph(without(C, 'i-extra'))
await page.waitForTimeout(120)
const exiting = await scale('i-extra')
check(exiting !== null && exiting > 0 && exiting < 1, `removed instance is shrinking (scale=${exiting?.toFixed(3)})`)
await page.waitForTimeout(600)
check((await scale('i-extra')) === null, 'removed instance is gone once its exit ends')
await settle()

// 4. A write API event flies a particle once the next graph arrives, and the particle lands.
sendEvent('RunInstances')
sendGraph(C)
await page.waitForTimeout(100)
const flying = await page.evaluate(() => window.__scene.flying())
check(flying > 0, `API event shows a particle in flight (${flying})`)
await page.locator('#stage').screenshot({ path: resolve(out, 'live-api-fly-light.png') })
await page.waitForTimeout(900)
check((await page.evaluate(() => window.__scene.flying())) === 0, 'particle lands and is removed')
await settle()

// 5. The scene renders no frames while idle.
const f0 = await page.evaluate(() => window.__scene.frames())
await page.waitForTimeout(10_000)
const idle = (await page.evaluate(() => window.__scene.frames())) - f0
check(idle === 0, `no frames over 10 s idle (${idle})`)

// 6. Clicking the instance opens its panel; deleting it marks the panel; Esc closes it.
// screenPoint is the base centre; the security group badge sits on the instance's top, so aim low.
const p = await page.evaluate((id) => window.__scene.screenPoint(id), instance.id)
await page.mouse.click(p.x, p.y - 2)
await page.waitForSelector('#property-panel', { timeout: 3_000 }).catch(() => {})
const panelId = await page.evaluate(() => document.querySelector('#property-panel')?.dataset.id ?? null)
check(panelId === instance.id, `panel shows the clicked instance (${panelId})`)
check(await page.locator('#panel-warnings').isVisible(), 'panel lists the instance warnings')
await page.screenshot({ path: resolve(out, 'live-panel-light.png') })
sendGraph(without(C, instance.id))
await page.waitForSelector('#panel-deleted', { timeout: 3_000 }).catch(() => {})
check(await page.locator('#panel-deleted').isVisible(), 'panel says the resource was deleted')
await page.keyboard.press('Escape')
check((await page.locator('#property-panel').count()) === 0, 'Esc closes the panel')

// 7. Screenshots of the full lab state in both themes.
sendGraph(C)
await settle()
await page.screenshot({ path: resolve(out, 'live-light.png') })
await page.emulateMedia({ colorScheme: 'dark' })
await settle()
await page.screenshot({ path: resolve(out, 'live-dark.png') })
console.log('saved live-light.png, live-dark.png, live-panel-light.png, live-api-fly-light.png to', out)

if (errors.length) console.log('page errors:\n' + errors.join('\n'))
await browser.close()
process.exit(failed || errors.length ? 1 : 0)
