// Practice mode through the real panel: copying the command never runs it.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiEvent, ResourceGraph } from '../graph/types'
import { THEMES } from '../scene/theme'
import * as api from './builder-api'
import { BuilderPanel } from './builder-panel'
import { NAME_HINT_MS, actionOf, lastWrite } from './command-panel'
import { fixedDraft } from './form-model'
import { LAB, golden, op } from './test-fixtures'
import { PREVIEW_DEBOUNCE_MS, useBuilder, type BuilderState } from './use-builder'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const draft = fixedDraft(op('create-route'), { routeTableId: 'rtb-1', targetId: 'igw-1', destination: '0.0.0.0/0' })
const preview: api.Preview = { command: 'aws ec2 create-route ...', argv: ['aws'], problems: [], practiceExpect: { edge: 'route:rtb-1->igw-1:0.0.0.0/0' } }
const events: ApiEvent[] = [{ service: 'ec2', action: 'DescribeVpcs', seq: 3, write: false }]

let seen: BuilderState
function Harness({ graph, evs = events, chatBusy = false }: { graph: ResourceGraph; evs?: ApiEvent[]; chatBusy?: boolean }) {
  const b = useBuilder(graph)
  seen = b.state
  if (b.state.phase === 'idle') b.dispatch({ type: 'open', draft })
  return 'draft' in b.state ? (
    <BuilderPanel state={b.state} graph={graph} lab={LAB} events={evs} theme={THEMES.light} dispatch={b.dispatch} onRun={b.run} chatBusy={chatBusy} />
  ) : null
}

describe('practice mode', () => {
  let root: Root
  let host: HTMLElement
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('turns Run and the practice toggle off while the chat runs a step', async () => {
    localStorage.setItem('cloudy-labs:practice', '0')
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview)
    act(() => root.render(<Harness graph={golden()} chatBusy />))
    await act(async () => vi.advanceTimersByTimeAsync(PREVIEW_DEBOUNCE_MS + 1))
    expect((host.querySelector('#run-command') as HTMLButtonElement).disabled).toBe(true)
    expect((host.querySelector('#practice-toggle') as HTMLInputElement).disabled).toBe(true)
    expect(host.querySelector('#chat-busy-note')).not.toBeNull()
    act(() => root.render(<Harness graph={golden()} />))
    expect((host.querySelector('#run-command') as HTMLButtonElement).disabled).toBe(false)
  })

  it('hands the command to the terminal and never calls runOp', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview)
    const runOp = vi.spyOn(api, 'runOp')
    const g = golden()
    act(() => root.render(<Harness graph={g} />))
    await act(async () => vi.advanceTimersByTimeAsync(PREVIEW_DEBOUNCE_MS + 1))
    expect(host.querySelector('#run-command')).not.toBeNull()

    act(() => (host.querySelector('#practice-toggle') as HTMLInputElement).click())
    expect(host.querySelector('#run-command')).toBeNull()
    expect(localStorage.getItem('cloudy-labs:practice')).toBe('1')

    act(() => (host.querySelector('#copy-command') as HTMLButtonElement).click())
    expect(seen).toMatchObject({ phase: 'practicing', since: 3 })
    expect(host.querySelector('#builder-status')?.textContent).toContain('Dán lệnh vào terminal')

    const withEdge = { ...g, version: g.version + 1, edges: [...g.edges, { id: 'route:rtb-1->igw-1:0.0.0.0/0', kind: 'route' as const, from: 'rtb-1', to: 'igw-1', label: '' }] }
    act(() => root.render(<Harness graph={withEdge} />))
    expect(seen).toMatchObject({ phase: 'done', outcome: null })
    expect(runOp).not.toHaveBeenCalled()
  })

  it('does not hand over a command the server refused', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue({ ...preview, problems: [{ field: 'destination', message: 'no' }] })
    act(() => root.render(<Harness graph={golden()} />))
    await act(async () => vi.advanceTimersByTimeAsync(PREVIEW_DEBOUNCE_MS + 1))
    act(() => (host.querySelector('#practice-toggle') as HTMLInputElement).click())
    expect((host.querySelector('#copy-command') as HTMLButtonElement).disabled).toBe(true)
    expect(seen.phase).toBe('form')
  })

  it('suggests checking the name once the call arrived but the scene stays the same', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview)
    const g = golden()
    act(() => root.render(<Harness graph={g} />))
    await act(async () => vi.advanceTimersByTimeAsync(PREVIEW_DEBOUNCE_MS + 1))
    act(() => (host.querySelector('#practice-toggle') as HTMLInputElement).click())
    act(() => (host.querySelector('#copy-command') as HTMLButtonElement).click())
    act(() => root.render(<Harness graph={g} evs={[...events, { service: 'ec2', action: 'CreateRoute', seq: 4, write: true }]} />))
    expect(host.querySelector('#practice-seen')?.textContent).toContain('ec2 CreateRoute')
    await act(async () => vi.advanceTimersByTimeAsync(NAME_HINT_MS - 1))
    expect(host.querySelector('#practice-name-hint')).toBeNull()
    await act(async () => vi.advanceTimersByTimeAsync(1))
    expect(host.querySelector('#practice-name-hint')?.textContent).toContain('Name tag')
    expect(seen.phase).toBe('practicing')
  })

  it('remembers the toggle, and works when storage throws', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview)
    localStorage.setItem('cloudy-labs:practice', '1')
    act(() => root.render(<Harness graph={golden()} />))
    expect((host.querySelector('#practice-toggle') as HTMLInputElement).checked).toBe(true)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    act(() => (host.querySelector('#practice-toggle') as HTMLInputElement).click())
    expect((host.querySelector('#practice-toggle') as HTMLInputElement).checked).toBe(false)
  })
})

describe('api events in practice', () => {
  it('names the API action an op calls', () => {
    expect(actionOf('run-instances')).toBe('RunInstances')
    expect(actionOf('authorize-security-group-ingress')).toBe('AuthorizeSecurityGroupIngress')
  })

  it('shows the newest write since the command was copied', () => {
    const evs: ApiEvent[] = [
      { service: 'ec2', action: 'CreateVpc', seq: 1, write: true },
      { service: 'ec2', action: 'RunInstances', seq: 5, write: true },
      { service: 'ec2', action: 'DescribeInstances', seq: 6, write: false },
    ]
    expect(lastWrite(evs, 1)?.action).toBe('RunInstances')
    expect(lastWrite(evs, 5)).toBeNull()
  })
})
