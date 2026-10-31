import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectGraph, RETRY_MAX_MS, RETRY_MIN_MS, wsUrl } from './graph-client'
import type { ApiEvent, ResourceGraph } from './types'

class FakeSocket {
  static all: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor(public url: string) {
    FakeSocket.all.push(this)
  }
  close() {
    this.closed = true
    this.onclose?.()
  }
  // Test helpers: what the server does.
  open() {
    this.onopen?.()
  }
  send(msg: object) {
    this.onmessage?.({ data: JSON.stringify(msg) })
  }
  drop() {
    this.onclose?.()
  }
}

const graph = (version: number): ResourceGraph => ({
  version,
  takenAt: '2026-10-29T00:00:00Z',
  emulator: 'floci',
  status: 'ok',
  nodes: [{ id: 'us-east-1', kind: 'region', label: 'us-east-1', props: {} }],
  contains: [],
  edges: [],
  warnings: [],
})

describe('connectGraph', () => {
  const makeHandlers = () => ({
    onGraph: vi.fn<(g: ResourceGraph) => void>(),
    onApiEvent: vi.fn<(e: ApiEvent) => void>(),
    onOpenChange: vi.fn<(open: boolean) => void>(),
  })
  let handlers: ReturnType<typeof makeHandlers>
  beforeEach(() => {
    vi.useFakeTimers()
    FakeSocket.all = []
    handlers = makeHandlers()
  })
  afterEach(() => vi.useRealTimers())
  const connect = () => connectGraph('ws://x/ws', handlers, FakeSocket as unknown as typeof WebSocket)

  it('builds the WebSocket URL from the page origin', () => {
    expect(wsUrl('http://127.0.0.1:5174')).toBe('ws://127.0.0.1:5174/ws')
    expect(wsUrl('https://labs.example')).toBe('wss://labs.example/ws')
  })

  it('accepts only newer graph versions and passes API events through', () => {
    connect()
    const s = FakeSocket.all[0]
    s.open()
    s.send({ type: 'graph', graph: graph(2) })
    s.send({ type: 'graph', graph: graph(1) })
    s.send({ type: 'graph', graph: graph(3) })
    s.send({ type: 'api-event', service: 'ec2', action: 'CreateVpc', seq: 7, write: true })
    expect(handlers.onGraph.mock.calls.map(([g]) => g.version)).toEqual([2, 3])
    expect(handlers.onApiEvent).toHaveBeenCalledWith({ service: 'ec2', action: 'CreateVpc', seq: 7, write: true })
    expect(handlers.onOpenChange).toHaveBeenCalledWith(true)
  })

  it('reconnects with growing backoff and accepts a restarted server counting from 1', () => {
    connect()
    FakeSocket.all[0].open()
    FakeSocket.all[0].send({ type: 'graph', graph: graph(5) })
    FakeSocket.all[0].drop()
    expect(handlers.onOpenChange).toHaveBeenLastCalledWith(false)
    vi.advanceTimersByTime(RETRY_MIN_MS)
    expect(FakeSocket.all).toHaveLength(2)
    FakeSocket.all[1].drop() // fails before opening: the next wait doubles
    vi.advanceTimersByTime(RETRY_MIN_MS)
    expect(FakeSocket.all).toHaveLength(2)
    vi.advanceTimersByTime(RETRY_MIN_MS)
    expect(FakeSocket.all).toHaveLength(3)
    FakeSocket.all[2].open()
    FakeSocket.all[2].send({ type: 'graph', graph: graph(1) })
    expect(handlers.onGraph.mock.calls.map(([g]) => g.version)).toEqual([5, 1])
  })

  it('caps the backoff', () => {
    connect()
    for (let i = 0; i < 10; i++) {
      FakeSocket.all.at(-1)!.drop()
      vi.advanceTimersByTime(RETRY_MAX_MS)
    }
    expect(FakeSocket.all).toHaveLength(11)
  })

  it('stops reconnecting once closed', () => {
    const close = connect()
    close()
    expect(FakeSocket.all[0].closed).toBe(true)
    vi.advanceTimersByTime(RETRY_MAX_MS * 2)
    expect(FakeSocket.all).toHaveLength(1)
  })

  it('passes twin messages through and ignores a malformed one', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const onTwin = vi.fn()
    connectGraph('ws://x/ws', { ...handlers, onTwin }, FakeSocket as unknown as typeof WebSocket)
    const s = FakeSocket.all[0]
    const twin = { lab: 'lab-a', attempt: 2, checks: [], ghosts: [], bound: {} }
    s.send({ type: 'twin', twin })
    s.send({ type: 'twin', twin: { ...twin, checks: [{ id: 'c', status: 'unknown' }] } })
    expect(onTwin.mock.calls).toEqual([[twin]])
    expect(err).toHaveBeenCalledTimes(1)
    err.mockRestore()
  })

  it('ignores a malformed graph', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    connect()
    FakeSocket.all[0].send({ type: 'graph', graph: { nodes: [] } })
    expect(handlers.onGraph).not.toHaveBeenCalled()
    expect(err).toHaveBeenCalled()
    err.mockRestore()
  })
})
