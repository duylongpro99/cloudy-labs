// End-to-end: build fixture-lab-06 through the builder alone, against the real lab-server and
// Floci. Every resource is dragged from the palette, every edge drawn from the connect handle,
// every attribute set from the property panel, and every command runs only when Run is pressed.
// Usage: node scripts/e2e-builder-lab-06.mjs [out-dir]
//   needs `labctl up`, `labctl start fixture-lab-06`, `labctl serve` (:8730) and `pnpm dev` (:5174);
//   server/tests/test_builder_e2e_docker.py sets all of that up and then runs `labctl check`.
// Writes <out-dir>/e2e-builder.json (every step: op, command, exit code, Run-to-scene time).
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5174/'
const out = resolve(process.argv[2] ?? '../plans/261029-1525-m3-builder-lab-06/notes')
mkdirSync(out, { recursive: true })
const REGION = 'us-east-1'
const DONE_MS = 15_000 // the panel gives up after 5 s and says so; this only bounds a hung page
const NAT_READY_MS = 120_000

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && !m.location().url.endsWith('/favicon.ico') && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))

// Every /api/run request and response, to prove nothing runs before Run and that the panel shows
// the command the server ran.
let runClicks = 0
const runRequests = []
const runResponses = []
page.on('request', (r) => r.url().endsWith('/api/run') && runRequests.push({ clicksBefore: runClicks, body: r.postDataJSON() }))
page.on('response', async (r) => r.url().endsWith('/api/run') && runResponses.push(await r.json().catch(() => null)))

const steps = []
let failed = false
const check = (ok, what) => {
  failed ||= !ok
  console.log(`${ok ? 'PASS' : 'FAIL'} ${what}`)
  return ok
}
const fail = (what) => {
  check(false, what)
  throw new Error(what)
}

const probe = (fn, ...args) => page.evaluate(([fn, args]) => window.__scene[fn](...args), [fn, args])
const visible = (sel) => page.locator(sel).isVisible().catch(() => false)

// The camera frames the scene once; as the lab grows, objects drift to the edges or under the
// panels, so fit the view again (the "Vừa khung" button) before reaching for anything.
async function closePanels() {
  if (await visible('#close-builder')) await page.click('#close-builder')
  if (await visible('#close-panel')) await page.click('#close-panel')
  await page.click('#fit-view')
  await page.waitForTimeout(700)
}

async function onCanvas(p, what) {
  const hit = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.tagName ?? null, p)
  if (hit !== 'CANVAS') fail(`${what} at (${Math.round(p.x)}, ${Math.round(p.y)}) is covered or off-screen (${hit})`)
  return p
}

async function pointFor(fn, id) {
  for (let i = 0; i < 40; i++) {
    const p = await probe(fn, id)
    if (p) return p
    await page.waitForTimeout(250)
  }
  fail(`${fn}(${id}) found nothing in the scene`)
}

async function gesture(from, to) {
  await onCanvas(to, 'drop point')
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(to.x, to.y, { steps: 16 })
  await page.waitForTimeout(150)
  const ok = await page.locator('#drag-ghost').getAttribute('data-ok').catch(() => null)
  const hint = await page.textContent('#drag-ghost').catch(() => '')
  await page.mouse.up()
  if (ok !== 'true') fail(`drop refused: ${hint || (await page.textContent('#builder-notice').catch(() => ''))}`)
}

async function expectForm(op) {
  await page.waitForSelector(`#build-form[data-op="${op}"]`, { timeout: 5_000 }).catch(() => fail(`no ${op} form`))
}

// Drag a palette kind onto a free spot of a tray and wait for its form.
async function drop(kind, trayId, op) {
  await closePanels()
  const button = await page.locator(`#palette button[data-kind="${kind}"]`).boundingBox()
  await gesture({ x: button.x + 12, y: button.y + 12 }, await pointFor('freePoint', trayId))
  await expectForm(op)
}

async function select(id) {
  await closePanels()
  const p = await onCanvas(await pointFor('screenPoint', id), id)
  await page.mouse.click(p.x, p.y - 2)
  await page.waitForSelector('#property-panel', { timeout: 3_000 }).catch(() => fail(`clicking ${id} selected nothing`))
}

// Select the source, drag its connect handle onto the target ([probe, id]), wait for the form.
// dy shifts the target point up, off an object drawn in front of the target.
async function connect(sourceId, [fn, targetId, dy = 0], op) {
  await select(sourceId)
  const at = await pointFor(fn, targetId)
  const to = { x: at.x, y: at.y + dy }
  await page.waitForFunction(() => window.__scene.handlePoint(), null, { timeout: 3_000 }).catch(() => fail(`${sourceId} shows no connect handle`))
  await gesture(await onCanvas(await probe('handlePoint'), 'connect handle'), to)
  await expectForm(op)
}

async function fill(field, value) {
  const el = page.locator(`#field-${field}`)
  if ((await el.evaluate((e) => e.tagName)) === 'SELECT') await el.selectOption(value)
  else await el.fill(value)
}

// Wait for a clean preview, press Run, wait until the collector's graph shows the change.
async function run(label) {
  await page.waitForFunction(() => document.querySelector('#run-command') && !document.querySelector('#run-command').disabled, null, { timeout: 5_000 })
    .catch(async () => fail(`${label}: Run stays disabled (${await page.textContent('#build-form').catch(() => '')})`))
  const shown = await page.textContent('#builder-command')
  const op = await page.locator('#build-form').getAttribute('data-op')
  check(runRequests.length === runClicks, `${label}: no /api/run before Run is pressed`)
  runClicks++
  const t0 = Date.now()
  await page.click('#run-command')
  await page.waitForSelector('#command-panel[data-phase="done"], #command-panel[data-phase="failed"]', { timeout: DONE_MS })
    .catch(() => fail(`${label}: no outcome after ${DONE_MS} ms`))
  const ms = Date.now() - t0
  const phase = await page.locator('#command-panel').getAttribute('data-phase')
  const res = runResponses.at(-1)
  const step = { label, op, command: shown, exitCode: res?.exitCode ?? null, cliMs: res?.durationMs ?? null, ms, phase }
  steps.push(step)
  console.log(`  ${String(steps.length).padStart(2)} ${label.padEnd(30)} ${phase.padEnd(6)} ${ms} ms (aws CLI ${step.cliMs} ms)`)
  check(res?.command === shown, `${label}: the panel shows the command the server ran`)
  if (phase !== 'done') fail(`${label}: ${await page.textContent('#builder-status')} ${res?.stderr ?? ''}`)
  return res?.expect?.node ?? null
}

// Waiting is not a builder action, so read the state from the lab-server's latest graph.
async function waitNatAvailable(nat) {
  const deadline = Date.now() + NAT_READY_MS
  const state = () => page.evaluate(async (id) => {
    const g = await (await fetch('/api/graph')).json()
    return g.nodes.find((n) => n.id === id)?.props?.state ?? null
  }, nat)
  let last
  while ((last = await state()) !== 'available') {
    if (Date.now() > deadline) fail(`${nat} is ${last} after ${NAT_READY_MS / 1000} s`)
    await page.waitForTimeout(1000)
  }
}

try {
  await page.goto(BASE)
  await page.waitForSelector('#palette button', { timeout: 30_000 })
  await page.waitForFunction(() => window.__scene?.freePoint, null, { timeout: 30_000 })
  await page.waitForTimeout(800)

  // VPC and DNS hostnames.
  await drop('vpc', REGION, 'create-vpc')
  await fill('name', 'lab06-vpc')
  check((await page.inputValue('#field-cidr')) === '10.66.0.0/16', 'VPC form suggests the lab CIDR')
  const vpc = await run('create-vpc')
  await select(vpc)
  await page.click('#action-dns-hostnames')
  await expectForm('modify-vpc-attribute')
  await run('enable-dns-hostnames')

  // Four subnets. The first one starts outside the VPC, which validation must stop before Run.
  const subnets = {}
  const plan = [
    ['public-a', '10.66.1.0/24', `${REGION}a`],
    ['public-b', '10.66.2.0/24', `${REGION}b`],
    ['private-a', '10.66.11.0/24', `${REGION}a`],
    ['private-b', '10.66.12.0/24', `${REGION}b`],
  ]
  for (const [name, cidr, az] of plan) {
    await drop('subnet', vpc, 'create-subnet')
    await fill('name', `lab06-${name}`)
    await fill('az', az)
    if (name === 'public-a') {
      await fill('cidr', '10.99.1.0/24')
      await page.waitForSelector('#problem-cidr', { timeout: 3_000 }).catch(() => {})
      check(/outside/.test((await page.textContent('#problem-cidr').catch(() => '')) ?? ''), 'a subnet outside the VPC is explained')
      check(await page.locator('#run-command').isDisabled(), 'Run is disabled while the form has a problem')
      check(runRequests.length === runClicks, 'nothing was sent for the wrong subnet')
    }
    await fill('cidr', cidr)
    subnets[name] = await run(`create-subnet ${name}`)
  }
  for (const name of ['public-a', 'public-b']) {
    await select(subnets[name])
    await page.click('#action-public-ip')
    await expectForm('modify-subnet-attribute')
    await run(`map-public-ip ${name}`)
  }

  // Internet Gateway, attached by an edge onto the VPC.
  await drop('igw', REGION, 'create-internet-gateway')
  await fill('name', 'lab06-igw')
  const igw = await run('create-internet-gateway')
  await connect(igw, ['freePoint', vpc], 'attach-internet-gateway')
  await run('attach-internet-gateway')

  // Elastic IP, route tables, the public route and its associations. A subnet only counts as
  // public once its route table reaches the Internet Gateway, and the NAT Gateway must sit in a
  // public subnet, so routing the public side comes before the NAT Gateway.
  await drop('elastic-ip', REGION, 'allocate-address')
  await fill('name', 'lab06-eip')
  await run('allocate-address')
  const tables = {}
  for (const side of ['public', 'private']) {
    await drop('route-table', vpc, 'create-route-table')
    await fill('name', `lab06-rt-${side}`)
    tables[side] = await run(`create-route-table ${side}`)
  }
  await connect(tables.public, ['screenPoint', igw], 'create-route')
  check((await page.inputValue('#field-destination')) === '0.0.0.0/0', 'a route defaults to 0.0.0.0/0')
  await run('route public -> igw')
  for (const name of ['public-a', 'public-b']) {
    await connect(tables.public, ['freePoint', subnets[name]], 'associate-route-table')
    await run(`associate ${name}`)
  }

  // NAT Gateway in public-a with the Elastic IP; route the private side to it once it is available.
  await drop('nat', subnets['public-a'], 'create-nat-gateway')
  await fill('name', 'lab06-nat')
  const nat = await run('create-nat-gateway')
  await waitNatAvailable(nat)
  await connect(tables.private, ['screenPoint', nat, -14], 'create-route') // its Elastic IP sits in front
  await run('route private -> nat')
  for (const name of ['private-a', 'private-b']) {
    await connect(tables.private, ['freePoint', subnets[name]], 'associate-route-table')
    await run(`associate ${name}`)
  }
  await closePanels()
  await page.screenshot({ path: resolve(out, 'e2e-builder-lab-06.png') })
} catch (e) {
  console.log(`stopped: ${e.message}`)
  failed = true
  await page.screenshot({ path: resolve(out, 'e2e-builder-lab-06-failed.png') }).catch(() => {})
}

const times = steps.map((s) => s.ms).sort((a, b) => a - b)
const p95 = times.length ? times[Math.min(times.length - 1, Math.ceil(0.95 * times.length) - 1)] : null
check(steps.length === 20, `20 steps run through the builder (${steps.length})`)
check(runRequests.length === runClicks, `one /api/run per Run press (${runRequests.length} requests, ${runClicks} presses)`)
console.log(`Run -> scene: p50 ${times[Math.floor(times.length / 2)]} ms, p95 ${p95} ms, max ${times.at(-1)} ms`)
writeFileSync(resolve(out, 'e2e-builder.json'), JSON.stringify({ steps, p95, errors }, null, 2) + '\n')
if (errors.length) console.log('page errors:\n' + errors.join('\n'))
await browser.close()
process.exit(failed || errors.length ? 1 : 0)
