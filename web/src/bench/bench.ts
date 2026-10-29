// Benchmark configuration, statistics and result export.
// Same method as the M0 render spike, so results compare directly.
// URL: ?view=bench&mode=bench&post=full&theme=dark&dpr=2&run=1   (mode=view for a normal interactive scene,
// mode=idle to count frames rendered while the scene stands still).
// Add &suite=1 to walk through every configuration in SUITE, one fresh page load per run.
import type { ThemeName } from '../scene/theme'

export type PostLevel = 'full' | 'lite' | 'flat'
export type Mode = 'view' | 'bench' | 'idle'

export interface BenchConfig {
  mode: Mode
  post: PostLevel
  theme: ThemeName
  dpr: number
  run: number
  durationMs: number
  warmupMs: number
  suiteIndex: number | null
  zoom: number | null // optional camera zoom override, used for close-up screenshots
}

export const CANVAS = { width: 1280, height: 800 } // fixed CSS size so every run pushes the same pixels

export function readConfig(search = location.search): BenchConfig {
  const q = new URLSearchParams(search)
  const pick = <T extends string>(k: string, allowed: readonly T[], d: T) => {
    const v = q.get(k) as T | null
    return v && allowed.includes(v) ? v : d
  }
  return {
    mode: pick('mode', ['view', 'bench', 'idle'] as const, 'view'),
    post: pick('post', ['full', 'lite', 'flat'] as const, 'full'),
    theme: pick('theme', ['light', 'dark'] as const, 'light'),
    dpr: Number(q.get('dpr') ?? 2) === 1 ? 1 : 2,
    run: Number(q.get('run') ?? 1),
    durationMs: Number(q.get('duration') ?? 10_000),
    warmupMs: Number(q.get('warmup') ?? 2_000),
    suiteIndex: q.has('suite') ? Number(q.get('i') ?? 0) : null,
    zoom: q.has('zoom') ? Number(q.get('zoom')) : null,
  }
}

const POSTS: PostLevel[] = ['full', 'lite', 'flat']
const THEMES: ThemeName[] = ['light', 'dark']
export const SUITE: string[] = [
  ...POSTS.flatMap((post) => THEMES.flatMap((theme) => [1, 2].map((dpr) => `view=bench&mode=bench&post=${post}&theme=${theme}&dpr=${dpr}&run=1`))),
  // Idle waits until the entrance animation and the shadow refresh that follows it have settled.
  'view=bench&mode=idle&post=full&theme=light&dpr=2&run=1&warmup=4000',
]

export function browserName(ua = navigator.userAgent): string {
  if (/Edg\//.test(ua)) return 'edge'
  if (/Chrome\//.test(ua)) return 'chrome'
  if (/Safari\//.test(ua) && /Version\//.test(ua)) return 'safari'
  if (/Firefox\//.test(ua)) return 'firefox'
  return 'unknown'
}

export interface FrameSample {
  dt: number // ms since the previous frame
  calls: number
  triangles: number
}

const pct = (sorted: number[], p: number) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))]
const round = (v: number) => Math.round(v * 100) / 100

export function summarize(cfg: BenchConfig, samples: FrameSample[], extra: Record<string, unknown>) {
  const dts = samples.map((s) => s.dt).sort((a, b) => a - b)
  const total = samples.reduce((a, s) => a + s.dt, 0)
  const calls = samples.map((s) => s.calls).sort((a, b) => a - b)
  const tris = samples.map((s) => s.triangles).sort((a, b) => a - b)
  return {
    browser: browserName(),
    post: cfg.post,
    theme: cfg.theme,
    dpr: cfg.dpr,
    run: cfg.run,
    mode: cfg.mode,
    frames: samples.length,
    frameTimeMs: dts.length ? { p50: round(pct(dts, 0.5)), p95: round(pct(dts, 0.95)), p99: round(pct(dts, 0.99)), max: round(dts[dts.length - 1]) } : null,
    avgFps: total ? round((samples.length * 1000) / total) : 0,
    drawCalls: calls.length ? { p50: pct(calls, 0.5), max: calls[calls.length - 1] } : null,
    triangles: tris.length ? { p50: pct(tris, 0.5), max: tris[tris.length - 1] } : null,
    canvasCss: CANVAS,
    windowDevicePixelRatio: devicePixelRatio,
    userAgent: navigator.userAgent,
    measuredAt: new Date().toISOString(),
    ...extra,
  }
}

export type BenchResult = ReturnType<typeof summarize>

export function resultName(r: BenchResult) {
  return r.mode === 'idle' ? `${r.browser}-idle-run${r.run}` : `${r.browser}-${r.post}-${r.theme}-dpr${r.dpr}-run${r.run}`
}

// Saves through the dev-server endpoint (see vite.config.ts); the page also offers a download.
export async function publish(r: BenchResult) {
  ;(window as unknown as { __benchResult: BenchResult }).__benchResult = r
  try {
    await fetch(`/__results/${resultName(r)}.json`, { method: 'POST', body: JSON.stringify(r, null, 2) })
  } catch {
    // Saving is best effort; the JSON stays on the page for manual download.
  }
}

export function nextSuiteUrl(cfg: BenchConfig): string | null {
  if (cfg.suiteIndex === null) return null
  const next = cfg.suiteIndex + 1
  return next < SUITE.length ? `?${SUITE[next]}&suite=1&i=${next}` : null
}
