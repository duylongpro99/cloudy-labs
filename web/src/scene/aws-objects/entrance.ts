// Entrance and exit animation timing (PRD F3.6). Every id keeps its own start time, so an object
// that is half-way in when the placement list changes carries on from where it was; objects
// already on screen keep their size; removed objects shrink away before they are dropped.
export const ENTRANCE_MS = 450
export const STAGGER_MS = 4
export const EXIT_MS = 300

const OVERSHOOT = 1.4

// easeOutBack: a small overshoot, close to the spring the M0 blocks used.
export function entranceScale(t: number) {
  if (t <= 0) return 0.001
  if (t >= 1) return 1
  const u = t - 1
  return 1 + (OVERSHOOT + 1) * u * u * u + OVERSHOOT * u * u
}

// The entrance progress at which entranceScale first reaches `scale`; used to resume an entrance
// from the size an object had when it was interrupted. entranceScale rises monotonically up to 1
// on [0, 1 / (OVERSHOOT + 1)], so bisect there.
export function entranceProgressFor(scale: number) {
  let lo = 0
  let hi = 1 / (OVERSHOOT + 1)
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (entranceScale(mid) < scale) lo = mid
    else hi = mid
  }
  return hi
}

// easeInQuad down to zero.
export const exitScale = (t: number) => (t >= 1 ? 0 : 1 - Math.max(0, t) ** 2)

// Start time for each id: ids already present keep theirs, new ids start at `now`, staggered by their order.
export function entranceStarts(ids: readonly string[], starts: ReadonlyMap<string, number>, now: number): Map<string, number> {
  let fresh = 0
  return new Map(ids.map((id) => [id, starts.get(id) ?? now + fresh++ * STAGGER_MS]))
}

export interface Curve {
  enterMs: number
  exitMs: number
  enter: (t: number) => number // visibility while entering, 0 -> 1
  enterProgressFor: (v: number) => number // inverse of `enter`
  exit: (t: number) => number // share of the visibility left while exiting, 1 -> 0
}

export const SCALE_CURVE: Curve = { enterMs: ENTRANCE_MS, exitMs: EXIT_MS, enter: entranceScale, enterProgressFor: entranceProgressFor, exit: exitScale }
export const FADE_CURVE: Curve = {
  enterMs: EXIT_MS,
  exitMs: EXIT_MS,
  enter: (t) => Math.min(1, Math.max(0, t)),
  enterProgressFor: (v) => v,
  exit: (t) => Math.max(0, 1 - t),
}

export interface Visibility {
  value: number // scale or opacity factor
  done: boolean // no animation left for this id
}

// Tracks which ids are entering, shown or exiting. `update` takes the current item list; ids that
// left it stay in `exiting()` until their exit ends and `prune` drops them.
export class Presence<T extends { id: string }> {
  private starts = new Map<string, number>()
  private exits = new Map<string, { item: T; start: number; from: number }>()
  private items = new Map<string, T>()

  constructor(private curve: Curve) {}

  update(items: readonly T[], now: number, animate = true) {
    const next = new Map(items.map((it) => [it.id, it]))
    for (const [id, item] of this.items) {
      if (next.has(id)) continue
      this.exits.set(id, { item, start: now, from: this.get(id, now)?.value ?? 1 })
      this.starts.delete(id)
    }
    const fresh = items.filter((it) => !this.starts.has(it.id))
    const resumed = new Map<string, number>()
    for (const it of fresh) {
      const exit = this.exits.get(it.id)
      if (!exit) continue
      const v = exit.from * this.curve.exit((now - exit.start) / this.curve.exitMs)
      resumed.set(it.id, now - this.curve.enterProgressFor(v) * this.curve.enterMs)
      this.exits.delete(it.id)
    }
    const known = new Map([...this.starts, ...resumed])
    const newIds = fresh.filter((it) => !resumed.has(it.id)).map((it) => it.id)
    for (const [id, start] of entranceStarts(newIds, known, now)) known.set(id, animate ? start : -Infinity)
    this.starts = new Map(items.map((it) => [it.id, known.get(it.id)!]))
    this.items = next
  }

  get(id: string, now: number): Visibility | null {
    const start = this.starts.get(id)
    if (start !== undefined) {
      const t = (now - start) / this.curve.enterMs
      return { value: this.curve.enter(t), done: t >= 1 }
    }
    const exit = this.exits.get(id)
    if (!exit) return null
    const t = (now - exit.start) / this.curve.exitMs
    return { value: exit.from * this.curve.exit(t), done: t >= 1 }
  }

  exiting(): T[] {
    return [...this.exits.values()].map((e) => e.item)
  }

  // Drops exits that have finished; true when anything was dropped.
  prune(now: number): boolean {
    let dropped = false
    for (const [id, e] of this.exits) {
      if ((now - e.start) / this.curve.exitMs >= 1) dropped = this.exits.delete(id) || dropped
    }
    return dropped
  }
}
