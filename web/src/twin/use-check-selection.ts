// Which check the learner pressed in the check panel. A selection belongs to one attempt of one
// lab: after `labctl reset` or a different lab it is gone, as it is once the check is.
// Esc lets go, like it closes the property panel.
import { useCallback, useEffect, useState } from 'react'
import type { TwinState } from '../graph/types'

const attemptKey = (twin: TwinState | null) => (twin?.lab ? `${twin.lab}#${twin.attempt}` : null)

export function selectedCheck(pick: { id: string; attempt: string | null } | null, twin: TwinState | null): string | null {
  if (!pick || !twin || pick.attempt !== attemptKey(twin)) return null
  return twin.checks.some((c) => c.id === pick.id) ? pick.id : null
}

export function useCheckSelection(twin: TwinState | null): [string | null, (id: string | null) => void] {
  const [pick, setPick] = useState<{ id: string; attempt: string | null } | null>(null)
  const selected = selectedCheck(pick, twin)
  if (pick && !selected) setPick(null) // gone for good, even if the old attempt's twin came back
  const key = attemptKey(twin)
  const select = useCallback((id: string | null) => setPick(id ? { id, attempt: key } : null), [key])
  useEffect(() => {
    if (!selected) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPick(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected])
  return [selected, select]
}
