// The server's registry (GET /api/registry), fetched once per page load. Until it settles the live
// view holds its scene back, so no kind is drawn as a fallback that the server actually knows.
// If the fetch fails the bundled copy stays in use and the error is shown.
import { useEffect, useState } from 'react'
import { parseRegistry, setRegistry } from './registry'

export interface RegistryState {
  settled: boolean
  error: string | null
}

let loading: Promise<string | null> | null = null

function loadOnce(): Promise<string | null> {
  loading ??= fetch('/api/registry')
    .then(async (r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setRegistry(parseRegistry(await r.json()))
      return null
    })
    .catch((e: unknown) => `Không tải được danh mục tài nguyên (${e instanceof Error ? e.message : String(e)}); dùng bản đi kèm.`)
  return loading
}

export function useRegistry(): RegistryState {
  const [state, setState] = useState<RegistryState>({ settled: false, error: null })
  useEffect(() => {
    let live = true
    void loadOnce().then((error) => live && setState({ settled: true, error }))
    return () => {
      live = false
    }
  }, [])
  return state
}
