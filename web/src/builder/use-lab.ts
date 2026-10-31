// The lab the learner opened with `labctl start`, as the builder needs it (GET /api/lab).
// Fetched again whenever the window regains focus: the learner may have started another lab
// or a new attempt in the terminal meanwhile, and whenever `changed` does (the twin's lab and
// attempt, which the lab-server pushes as soon as either changes).
import { useEffect, useState } from 'react'
import { fetchLab, type LabInfo } from './builder-api'

export interface LabState {
  lab: LabInfo | null
  error: string | null
  loaded: boolean
}

export function useLab(changed: string | null = null): LabState {
  const [state, setState] = useState<LabState>({ lab: null, error: null, loaded: false })
  useEffect(() => {
    let live = true
    const load = () =>
      fetchLab().then(
        (lab) => live && setState({ lab, error: null, loaded: true }),
        (e: unknown) => live && setState({ lab: null, error: e instanceof Error ? e.message : String(e), loaded: true }),
      )
    void load()
    window.addEventListener('focus', load)
    return () => {
      live = false
      window.removeEventListener('focus', load)
    }
  }, [changed])
  return state
}
