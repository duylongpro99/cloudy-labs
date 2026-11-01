import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { ResourceGraph } from '../graph/types'
import { THEMES } from '../scene/theme'
import { ANALYSIS_NOTE, analyseReachability, type Reachability } from './reachability-api'
import { endpointOptions, ReachabilityPanel } from './reachability-panel'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const GRAPH: ResourceGraph = {
  version: 1,
  takenAt: '2026-10-31T00:00:00Z',
  emulator: 'floci',
  status: 'ok',
  nodes: [
    { id: 'i-web', kind: 'instance', label: 'rx-web', props: {} },
    { id: 'sg-web', kind: 'security-group', label: 'rx-sg-web', props: {} },
    { id: 'vpc-a', kind: 'vpc', label: 'rx-a', props: {} },
  ],
  contains: [],
  edges: [],
  warnings: [],
}

const BLOCKED: Reachability = {
  ok: false,
  blockedAt: 'sg-web',
  reason: 'no-matching-rule',
  label: 'analysed',
  hops: [
    { resource_id: 'internet', kind: 'internet', verdict: 'forward', reason: 'routed', rule: null },
    { resource_id: 'sg-web', kind: 'security-group', verdict: 'deny', reason: 'no-matching-rule', rule: null },
  ],
}

function reply(status: number, body: unknown, seen: RequestInit[] = []): typeof fetch {
  return (async (_path: string, init?: RequestInit) => {
    seen.push(init!)
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
}

function Harness({ fetcher, selected = null }: { fetcher: typeof fetch; selected?: string | null }) {
  const [result, setResult] = useState<Reachability | null>(null)
  return <ReachabilityPanel graph={GRAPH} selected={selected} theme={THEMES.light} result={result} onResult={setResult} fetcher={fetcher} />
}

describe('ReachabilityPanel', () => {
  let root: Root
  let host: HTMLElement
  beforeEach(() => {
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
  })
  const q = <T extends Element>(sel: string) => host.querySelector<T>(sel)!
  const type = (sel: string, value: string) =>
    act(() => {
      const input = q<HTMLInputElement>(sel)
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })

  it('offers internet and the endpoint kinds only', () => {
    expect(endpointOptions(GRAPH).map((o) => o.value)).toEqual(['internet', 'i-web'])
  })

  it('always says it is an analysis of configuration', () => {
    act(() => root.render(<Harness fetcher={reply(200, BLOCKED)} />))
    expect(q('.reach-note').textContent).toBe(ANALYSIS_NOTE)
  })

  it('sends the query and lists the hops with the blocking one marked', async () => {
    const seen: RequestInit[] = []
    act(() => root.render(<Harness fetcher={reply(200, BLOCKED, seen)} selected="i-web" />))
    act(() => q<HTMLButtonElement>('.reach-use-selected[data-end="dst"]').click())
    type('#reach-port', '22')
    await act(async () => q<HTMLButtonElement>('#reach-run').click())
    expect(JSON.parse(seen[0].body as string)).toEqual({ src: 'internet', dst: 'i-web', port: 22, proto: 'tcp' })
    expect(q('#reach-result').getAttribute('data-ok')).toBe('false')
    expect(q('#reach-result').textContent).toContain('Bị chặn tại rx-sg-web')
    const hops = [...host.querySelectorAll('.reach-hop')]
    expect(hops.map((h) => h.getAttribute('data-verdict'))).toEqual(['forward', 'deny'])
    expect(hops[0].textContent).toContain('Internet')
  })

  it('refuses a port out of range before sending', () => {
    act(() => root.render(<Harness fetcher={reply(200, BLOCKED)} />))
    type('#reach-dst', 'i-web')
    type('#reach-port', '70000')
    expect(q<HTMLButtonElement>('#reach-run').disabled).toBe(true)
  })

  it('shows the server refusal', async () => {
    act(() => root.render(<Harness fetcher={reply(422, { detail: "'nope' is no resource" })} />))
    type('#reach-dst', 'nope')
    await act(async () => q<HTMLButtonElement>('#reach-run').click())
    expect(q('#reach-error').textContent).toBe("Truy vấn không hợp lệ: 'nope' is no resource")
    expect(host.querySelector('#reach-result')).toBeNull()
  })
})

describe('analyseReachability', () => {
  it('posts JSON to the endpoint', async () => {
    const seen: RequestInit[] = []
    const r = await analyseReachability({ src: 'a', dst: 'b', port: 1, proto: 'udp' }, reply(200, BLOCKED, seen))
    expect(r.blockedAt).toBe('sg-web')
    expect(seen[0].method).toBe('POST')
    expect((seen[0].headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })
})
