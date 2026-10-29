// Browser checks for the builder in real Google Chrome, with the lab-server faked: /ws sends the
// lab 6 + 7 golden graph, /api/lab the fixture lab, /api/preview echoes a command, /api/run is
// recorded. Usage: node scripts/check-builder.mjs [out-dir]   (dev server on :5174)
// The real commands and their validation are covered by the server tests and the Docker e2e run.
import { mkdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5174/'
const out = resolve(process.argv[2] ?? '../plans/261029-1525-m3-builder-lab-06/notes')
mkdirSync(out, { recursive: true })

const golden = JSON.parse(readFileSync(new URL('../../server/tests/fixtures/graph/lab-06-07.graph.json', import.meta.url), 'utf8'))
const OPS = [
  { name: 'create-vpc', gesture: 'create', creates: 'vpc', containers: ['region'] },
  { name: 'create-subnet', gesture: 'create', creates: 'subnet', containers: ['vpc', 'az'] },
  { name: 'create-internet-gateway', gesture: 'create', creates: 'igw', containers: ['region'] },
  { name: 'attach-internet-gateway', gesture: 'connect', source: 'igw', targets: ['vpc'] },
  { name: 'allocate-address', gesture: 'create', creates: 'elastic-ip', containers: ['region'] },
  { name: 'create-nat-gateway', gesture: 'create', creates: 'nat', containers: ['subnet-public'] },
  { name: 'create-route-table', gesture: 'create', creates: 'route-table', containers: ['vpc'] },
  { name: 'create-route', gesture: 'connect', source: 'route-table', targets: ['igw', 'nat'] },
  { name: 'associate-route-table', gesture: 'connect', source: 'route-table', targets: ['subnet-public', 'subnet-private'] },
  { name: 'modify-vpc-attribute', gesture: 'attribute', targets: ['vpc'] },
  { name: 'modify-subnet-attribute', gesture: 'attribute', targets: ['subnet-public', 'subnet-private'] },
]
const LAB = {
  id: 'fixture-lab-06', title: 'Fixture lab 6', attempt: 7, tasks: [],
  palette: ['vpc', 'subnet', 'igw', 'elastic-ip', 'nat', 'route-table'], tags: { lab: 'fixture-lab-06' },
  cidrs: ['10.66.0.0/16'], ops: OPS, azs: ['us-east-1a', 'us-east-1b', 'us-east-1c'], canRun: true, runBlocker: null,
}
const PRIVATE_SUBNET = 'subnet-44acdeb7'

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, deviceScaleFactor: 2 })
const errors = []
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
const previews = []
const runs = []
await page.route('**/api/lab', (r) => r.fulfill({ json: LAB }))
await page.route('**/api/preview', (r) => {
  const body = r.request().postDataJSON()
  previews.push(body)
  const args = Object.entries(body.params).map(([k, v]) => `--${k} ${v}`).join(' ')
  r.fulfill({ json: { command: `aws ec2 ${body.op} ${args} --profile lab --output json`, argv: [], problems: [] } })
})
await page.route('**/api/run', (r) => {
  const body = r.request().postDataJSON()
  runs.push(body)
  r.fulfill({ json: { command: 'aws ...', argv: [], exitCode: 0, stdout: '{}', stderr: '', durationMs: 412, expect: { node: PRIVATE_SUBNET, prop: 'mapPublicIpOnLaunch', value: true } } })
})

const probe = (fn, ...args) => page.evaluate(([fn, args]) => window.__scene[fn](...args), [fn, args])
const nodeCount = () => page.evaluate(() => document.querySelector('#live-panel')?.textContent?.match(/(\d+) tài nguyên/)?.[1])
const settle = () => page.waitForTimeout(1200)
async function drag(from, to, steps = 12) {
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(to.x, to.y, { steps })
  await page.waitForTimeout(150)
}

await page.emulateMedia({ colorScheme: 'light' })
await page.goto(BASE)
while (!socket) await page.waitForTimeout(50)
sendGraph(golden)
await page.waitForFunction(() => window.__scene?.trayPoint, null, { timeout: 30_000 })
await settle()

// 1. The palette lists the lab's kinds.
const kinds = await page.locator('#palette button').evaluateAll((bs) => bs.map((b) => b.dataset.kind))
check(JSON.stringify(kinds) === JSON.stringify(LAB.palette), `palette shows the lab's kinds (${kinds.join(', ')})`)
const count0 = await nodeCount()

// 2. Dragging a VPC tints the region; dropping it there opens the form with the lab's CIDR.
const vpcButton = await page.locator('#palette button[data-kind="vpc"]').boundingBox()
const region = await probe('trayPoint', 'us-east-1')
const regionEdge = { x: region.x, y: region.y + 120 } // off the VPC trays, still on the region
await drag({ x: vpcButton.x + 10, y: vpcButton.y + 10 }, regionEdge)
check((await page.locator('#drag-ghost').getAttribute('data-ok')) === 'true', 'ghost says the region takes a VPC')
await page.screenshot({ path: resolve(out, 'builder-drag-light.png') })
await page.mouse.up()
await page.waitForSelector('#build-form', { timeout: 3_000 }).catch(() => {})
check((await page.locator('#build-form').getAttribute('data-op')) === 'create-vpc', 'drop opens the create-vpc form')
check((await page.inputValue('#field-cidr').catch(() => '')) === '10.66.0.0/16', 'form suggests the lab CIDR')
await page.waitForFunction(() => document.querySelector('#builder-command')?.textContent?.startsWith('aws ec2 create-vpc'), null, { timeout: 3_000 }).catch(() => {})
check((await page.textContent('#builder-command'))?.includes('--cidr 10.66.0.0/16'), 'preview shows the command for the form')

// 3. Editing the form previews again, once, after a pause.
const before = previews.length
await page.fill('#field-cidr', '10.67.0.0/16')
await page.waitForTimeout(500)
check(previews.length === before + 1 && previews.at(-1).params.cidr === '10.67.0.0/16', `edit previews once with the new CIDR (${previews.length - before})`)
check(runs.length === 0, 'nothing runs before Run is pressed')
check((await nodeCount()) === count0, 'the scene does not change on drop')
await page.screenshot({ path: resolve(out, 'builder-form-light.png') })
await page.keyboard.press('Escape')
check((await page.locator('#builder-panel').count()) === 0, 'Esc closes the form')

// 4. A NAT Gateway dropped on the region, outside any subnet, is refused with a reason.
const natButton = await page.locator('#palette button[data-kind="nat"]').boundingBox()
const az = golden.nodes.find((n) => n.kind === 'az' && n.id.startsWith('vpc-149d0439/'))
const azPoint = await probe('trayPoint', az.id)
await drag({ x: natButton.x + 10, y: natButton.y + 10 }, regionEdge)
check((await page.locator('#drag-ghost').getAttribute('data-ok')) === 'false', 'ghost says the region does not take a NAT Gateway')
await page.mouse.up()
const notice = await page.textContent('#builder-notice').catch(() => '')
check((await page.locator('#builder-panel').count()) === 0 && /NAT Gateway/.test(notice ?? ''), `wrong drop explains itself (${notice})`)

// 5. An edge from a route table to the IGW opens create-route with 0.0.0.0/0.
const rt = golden.nodes.find((n) => n.kind === 'route-table' && n.label === 'lab06-rt-private')
const rtPoint = await probe('screenPoint', rt.id)
await page.mouse.click(rtPoint.x, rtPoint.y - 2)
await page.waitForFunction(() => window.__scene.handlePoint(), null, { timeout: 3_000 }).catch(() => {})
const handle = await probe('handlePoint')
check(handle !== null, 'selected route table shows a connect handle')
const igw = await probe('screenPoint', 'igw-34ddd4cd')
await drag(handle, { x: igw.x, y: igw.y - 2 }, 20)
await page.screenshot({ path: resolve(out, 'builder-connect-light.png') })
await page.mouse.up()
await page.waitForSelector('#build-form', { timeout: 3_000 }).catch(() => {})
check((await page.locator('#build-form').getAttribute('data-op')) === 'create-route', 'edge opens the create-route form')
check((await page.inputValue('#field-destination').catch(() => '')) === '0.0.0.0/0', 'route defaults to 0.0.0.0/0')
check((await page.textContent('#field-targetId'))?.includes('igw-34ddd4cd'), 'route target is the IGW')
await page.keyboard.press('Escape')

// 6. The private subnet's panel offers public IPs; Run waits for the collector, then reports done.
await page.keyboard.press('Escape')
const sub = await probe('screenPoint', PRIVATE_SUBNET)
await page.mouse.click(sub.x, sub.y - 2)
await page.waitForSelector('#action-public-ip', { timeout: 3_000 }).catch(() => {})
check(await page.locator('#action-public-ip').isVisible(), 'private subnet panel offers "Tự gán IP public"')
await page.click('#action-public-ip')
await page.waitForFunction(() => !document.querySelector('#run-command')?.disabled, null, { timeout: 3_000 }).catch(() => {})
await page.click('#run-command')
await page.waitForSelector('#command-panel[data-phase="waiting"]', { timeout: 3_000 }).catch(() => {})
check(runs.length === 1 && runs[0].op === 'modify-subnet-attribute', 'Run sends modify-subnet-attribute')
check((await page.locator('#command-panel').getAttribute('data-phase')) === 'waiting', 'panel waits for the collector')
check((await page.textContent('#exit-code')) === '0', 'panel shows the exit code')
const changed = { ...golden, nodes: golden.nodes.map((n) => (n.id === PRIVATE_SUBNET ? { ...n, props: { ...n.props, mapPublicIpOnLaunch: true } } : n)) }
sendGraph(changed)
await page.waitForSelector('#command-panel[data-phase="done"]', { timeout: 3_000 }).catch(() => {})
check((await page.locator('#command-panel').getAttribute('data-phase')) === 'done', 'panel is done once the graph shows the change')
await page.screenshot({ path: resolve(out, 'builder-done-light.png') })

// 7. Dark theme while dragging.
await page.click('#close-builder')
await page.keyboard.press('Escape')
await page.emulateMedia({ colorScheme: 'dark' })
await settle()
const subnetButton = await page.locator('#palette button[data-kind="subnet"]').boundingBox()
await drag({ x: subnetButton.x + 10, y: subnetButton.y + 10 }, azPoint)
await page.screenshot({ path: resolve(out, 'builder-drag-dark.png') })
await page.mouse.up()
check((await page.locator('#build-form').getAttribute('data-op').catch(() => null)) === 'create-subnet', 'subnet dropped on an AZ opens create-subnet')
check((await page.textContent('#field-az').catch(() => ''))?.startsWith('us-east-1'), 'AZ is fixed by the tray')

if (errors.length) console.log('page errors:\n' + errors.join('\n'))
await browser.close()
process.exit(failed || errors.length ? 1 : 0)
