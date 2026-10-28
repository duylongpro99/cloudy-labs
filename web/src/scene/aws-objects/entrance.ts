// Entrance animation timing: each object scales up from its base, staggered by its order among the new objects.
// Objects already on screen keep their size when the placement list changes.
export const ENTRANCE_MS = 450
export const STAGGER_MS = 4

// easeOutBack: a small overshoot, close to the spring the M0 blocks used.
export function entranceScale(t: number) {
  if (t <= 0) return 0.001
  if (t >= 1) return 1
  const c = 1.4
  const u = t - 1
  return 1 + (c + 1) * u * u * u + c * u * u
}

// Start delay in ms for each id, or null for an id that has already been shown and should stay at full size.
export function entranceDelays(ids: readonly string[], shown: ReadonlySet<string>): (number | null)[] {
  let fresh = 0
  return ids.map((id) => (shown.has(id) ? null : fresh++ * STAGGER_MS))
}
