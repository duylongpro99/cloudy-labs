// End-to-end: build fixture-lab-07 through the builder alone, against the real lab-server and
// Floci, in one of two modes:
//   run       every command runs only when Run is pressed (one /api/run per press);
//   practice  the Luyện tập toggle is on: each command is copied from the panel and run here with
//             `bash -c`, as a learner would in a terminal; the page must never call /api/run.
// Usage: node scripts/e2e-builder-lab-07.mjs <run|practice> [out-dir]
//   needs `labctl up`, a fresh `labctl start fixture-lab-07`, the lab-server (:8730) and `pnpm dev`
//   (:5174); server/tests/test_builder_e2e_docker.py sets all of that up and then runs `labctl check`.
// Writes <out-dir>/e2e-builder-lab-07-<mode>.json (every step: op, command, exit code, time to scene).
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5174/'
const mode = process.argv[2]
if (mode !== 'run' && mode !== 'practice') {
  console.log('usage: node scripts/e2e-builder-lab-07.mjs <run|practice> [out-dir]')
  process.exit(2)
}
const practice = mode === 'practice'
const out = resolve(process.argv[3] ?? '../plans/261030-1045-m4-builder-lab-07/notes')
mkdirSync(out, { recursive: true })
const REGION = 'us-east-1'
const DONE_MS = 15_000 // a run gives up after 5 s and says so; this only bounds a hung page
const MY_IP = '203.0.113.10/32'

// The copied command runs with the lab profile's config only, as `labctl` sets up a terminal:
// no AWS_* setting of the machine may send it anywhere but the emulator.
const terminalEnv = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('AWS_') || k === 'AWS_CONFIG_FILE'))

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1320,1000'] })
const page = await browser.newPage({ viewport: { width: 1300, height: 960 }, acceptDownloads: true })
const errors = []
page.on('console', (m) => m.type() === 'error' && !m.location().url.endsWith('/favicon.ico') && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))

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
const graph = () => page.evaluate(async () => (await fetch('/api/graph')).json())
const nodeId = async (kind, label) => (await graph()).nodes.find((n) => n.kind === kind && n.label === label)?.id ?? null

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

async function connect(sourceId, targetId, op) {
  await select(sourceId)
  await page.waitForFunction(() => window.__scene.handlePoint(), null, { timeout: 3_000 }).catch(() => fail(`${sourceId} shows no connect handle`))
  await gesture(await onCanvas(await probe('handlePoint'), 'connect handle'), await pointFor('screenPoint', targetId))
  await expectForm(op)
}

async function fill(field, value) {
  const el = page.locator(`#field-${field}`)
  if ((await el.evaluate((e) => e.tagName)) === 'SELECT') await el.selectOption(value)
  else await el.fill(value)
}

// The preview is current and has no problem: the command shown is the one that would run.
async function cleanPreview(label) {
  await page.waitForFunction(
    () => document.querySelector('#builder-command')?.dataset.stale === 'false' && document.querySelector('#builder-command').textContent.startsWith('aws ')
      && !document.querySelector('[id^="problem-"]'),
    null,
    { timeout: 5_000 },
  ).catch(async () => fail(`${label}: no clean preview (${await page.textContent('#build-form').catch(() => '')})`))
}

async function outcome(label, t0) {
  await page.waitForSelector('#command-panel[data-phase="done"], #command-panel[data-phase="failed"]', { timeout: DONE_MS })
    .catch(() => fail(`${label}: no outcome after ${DONE_MS} ms`))
  return { ms: Date.now() - t0, phase: await page.locator('#command-panel').getAttribute('data-phase') }
}

// Run mode: press Run. Practice mode: press Copy, run the copied command in a shell, and wait
// for the panel to see it in the scene. Returns the step.
async function step(label) {
  await cleanPreview(label)
  const shown = await page.textContent('#builder-command')
  const op = await page.locator('#build-form').getAttribute('data-op')
  let s
  if (practice) {
    check(!(await visible('#run-command')), `${label}: practice mode offers no Run`)
    await page.click('#copy-command')
    await page.waitForSelector('#command-panel[data-phase="practicing"]', { timeout: 3_000 }).catch(() => fail(`${label}: Copy did not start practice`))
    const t0 = Date.now()
    let exitCode = 0
    let stdout = ''
    try {
      stdout = execFileSync('bash', ['-c', shown], { env: terminalEnv, encoding: 'utf8', timeout: 60_000 })
    } catch (e) {
      exitCode = e.status ?? -1
      console.log(e.stderr)
    }
    const cliMs = Date.now() - t0
    if (exitCode !== 0) fail(`${label}: the copied command failed in the shell (exit ${exitCode})`)
    const { ms, phase } = await outcome(label, t0)
    s = { label, op, command: shown, exitCode, cliMs, ms, phase, stdout }
  } else {
    await page.waitForFunction(() => !document.querySelector('#run-command')?.disabled, null, { timeout: 5_000 })
      .catch(() => fail(`${label}: Run stays disabled`))
    check(runRequests.length === runClicks, `${label}: no /api/run before Run is pressed`)
    runClicks++
    const t0 = Date.now()
    await page.click('#run-command')
    const { ms, phase } = await outcome(label, t0)
    const res = runResponses.at(-1)
    check(res?.command === shown, `${label}: the panel shows the command the server ran`)
    s = { label, op, command: shown, exitCode: res?.exitCode ?? null, cliMs: res?.durationMs ?? null, ms, phase, stdout: res?.stdout ?? '', expect: res?.expect }
  }
  steps.push(s)
  console.log(`  ${String(steps.length).padStart(2)} ${label.padEnd(30)} ${s.phase.padEnd(6)} ${s.ms} ms (aws CLI ${s.cliMs} ms)`)
  if (s.phase !== 'done') fail(`${label}: ${await page.textContent('#builder-status')}`)
  return s
}

// The id of what a step created: the run's expectation names it; in practice mode, the
// scene's node of that kind with the name typed.
async function created(s, kind, name) {
  return s.expect?.node ?? (await nodeId(kind, name)) ?? fail(`${name} is not in the graph`)
}

async function addRule(group, port, cidr, label) {
  await select(group)
  await page.click('#action-add-ingress')
  await expectForm('authorize-security-group-ingress')
  await fill('port', port)
  await fill('cidr', cidr)
  return step(label)
}

try {
  await page.goto(BASE)
  await page.waitForSelector('#palette button', { timeout: 30_000 })
  await page.waitForFunction(() => window.__scene?.freePoint, null, { timeout: 30_000 })
  await page.waitForTimeout(800)
  const vpc = (await nodeId('vpc', 'lab07-vpc')) ?? fail('lab07-vpc is missing: run `labctl start fixture-lab-07`')
  const subnet = (await nodeId('subnet-public', 'lab07-public')) ?? fail('lab07-public is missing or not public')

  // The web group: HTTP from anywhere; SSH from anywhere is refused before anything runs; SSH
  // from one address is fine.
  await drop('security-group', vpc, 'create-security-group')
  if (practice !== (await page.isChecked('#practice-toggle'))) await page.click('#practice-toggle')
  await fill('name', 'web')
  const web = await created(await step('create-security-group web'), 'security-group', 'web')
  await addRule(web, '80', '0.0.0.0/0', 'ingress web tcp 80 world')
  await select(web)
  await page.click('#action-add-ingress')
  await expectForm('authorize-security-group-ingress')
  await fill('port', '22')
  await fill('cidr', '0.0.0.0/0')
  await page.waitForSelector('#problem-cidr', { timeout: 3_000 }).catch(() => {})
  check(/SSH \(port 22\)/.test((await page.textContent('#problem-cidr').catch(() => '')) ?? ''), 'SSH open to the world is explained')
  if (!practice) check(await page.locator('#run-command').isDisabled(), 'Run is disabled for SSH open to the world')
  check(await page.locator('#copy-command').isDisabled(), 'Copy is disabled for SSH open to the world')
  await fill('cidr', MY_IP)
  await step('ingress web tcp 22 /32')

  // Key pair: in run mode the panel offers the private key once, as a download.
  await drop('key-pair', REGION, 'create-key-pair')
  await fill('name', 'lab07-key')
  const key = await step('create-key-pair')
  if (practice) {
    check(JSON.parse(key.stdout).KeyMaterial?.startsWith('-----BEGIN'), 'the terminal got the private key')
  } else {
    const [download] = await Promise.all([page.waitForEvent('download'), page.click('#download-pem')])
    check(download.suggestedFilename() === 'lab07-key.pem', `the key downloads as ${download.suggestedFilename()}`)
    const pem = readFileSync(await download.path(), 'utf8')
    check(pem.startsWith('-----BEGIN'), 'the download is the private key')
    await download.delete()
  }

  // The instance, in the public subnet with the web group, the key pair and the lab's UserData.
  await drop('instance', subnet, 'run-instances')
  await fill('name', 'lab07-web')
  check((await page.inputValue('#field-securityGroupId')) === web, 'the instance form picks the web group')
  check((await page.inputValue('#field-keyName')) === 'lab07-key', 'the instance form picks the key pair')
  check((await page.inputValue('#field-userData')).length > 0, 'the instance form fills in the lab UserData')
  const instance = await created(await step('run-instances'), 'instance', 'lab07-web')

  // A second group, attached by an edge onto the instance.
  await drop('security-group', vpc, 'create-security-group')
  await fill('name', 'admin')
  await fill('description', 'Lab admin access')
  const admin = await created(await step('create-security-group admin'), 'security-group', 'admin')
  await connect(admin, instance, 'modify-instance-attribute')
  const attach = await step('attach admin to instance')
  check(attach.command.includes(web) && attach.command.includes(admin), 'the command keeps the web group and adds admin')
  check((await graph()).edges.some((e) => e.id === `attached:${web}->${instance}`), 'the web group is still attached')

  await closePanels()
  await page.screenshot({ path: resolve(out, `e2e-builder-lab-07-${mode}.png`) })
} catch (e) {
  console.log(`stopped: ${e.message}`)
  failed = true
  await page.screenshot({ path: resolve(out, `e2e-builder-lab-07-${mode}-failed.png`) }).catch(() => {})
}

const times = steps.map((s) => s.ms).sort((a, b) => a - b)
check(steps.length === 7, `7 steps through the builder (${steps.length})`)
if (practice) check(runRequests.length === 0, `practice mode sent no /api/run (${runRequests.length})`)
else check(runRequests.length === runClicks, `one /api/run per Run press (${runRequests.length} requests, ${runClicks} presses)`)
console.log(`to scene: p50 ${times[Math.floor(times.length / 2)]} ms, max ${times.at(-1)} ms`)
// stdout of create-key-pair holds the private key: never write it down.
const record = steps.map(({ stdout, ...s }) => s)
writeFileSync(resolve(out, `e2e-builder-lab-07-${mode}.json`), JSON.stringify({ mode, steps: record, errors }, null, 2) + '\n')
if (errors.length) console.log('page errors:\n' + errors.join('\n'))
await browser.close()
process.exit(failed || errors.length ? 1 : 0)
