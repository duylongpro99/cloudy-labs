// Live resource graph from the lab-server WebSocket (/ws, proxied by Vite in development).
// The scene depends on this graph only (NFR4): it never talks to the emulator directly.
import { useEffect, useState } from 'react'
import { parseGraph, type ApiEvent, type ResourceGraph, type ServerMessage } from './types'

export type ConnectionState = 'connecting' | 'live' | 'emulator-down' | 'disconnected'

export interface GraphConnectionHandlers {
  onGraph: (g: ResourceGraph) => void
  onApiEvent: (e: ApiEvent) => void
  onOpenChange: (open: boolean) => void
}

export const RETRY_MIN_MS = 500
export const RETRY_MAX_MS = 5000

export function wsUrl(origin = location.origin) {
  return `${origin.replace(/^http/, 'ws')}/ws`
}

// Connects and keeps reconnecting with backoff until the returned function is called.
// Within one connection only a graph with a higher version is accepted; a new connection
// accepts whatever comes first, since a restarted server counts versions from 1 again.
export function connectGraph(url: string, h: GraphConnectionHandlers, Ws: typeof WebSocket = WebSocket): () => void {
  let ws: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let retry = RETRY_MIN_MS
  let closed = false

  const open = () => {
    let version = -1
    const sock = new Ws(url)
    ws = sock
    sock.onopen = () => {
      retry = RETRY_MIN_MS
      h.onOpenChange(true)
    }
    sock.onmessage = (m) => {
      let msg: ServerMessage
      try {
        msg = JSON.parse(String(m.data)) as ServerMessage
        if (msg.type === 'graph') msg = { ...msg, graph: parseGraph(msg.graph) }
      } catch (err) {
        console.error('[graph] bad message', err)
        return
      }
      if (msg.type === 'graph') {
        if (msg.graph.version <= version) return
        version = msg.graph.version
        h.onGraph(msg.graph)
      } else if (msg.type === 'api-event') {
        h.onApiEvent({ service: msg.service, action: msg.action, seq: msg.seq, write: !!msg.write })
      }
    }
    sock.onclose = () => {
      if (ws !== sock) return
      ws = null
      h.onOpenChange(false)
      if (closed) return
      timer = setTimeout(open, retry)
      retry = Math.min(retry * 2, RETRY_MAX_MS)
    }
  }
  open()
  return () => {
    closed = true
    clearTimeout(timer)
    const sock = ws
    ws = null
    sock?.close()
  }
}

const MAX_EVENTS = 16

export interface ResourceGraphState {
  graph: ResourceGraph | null
  state: ConnectionState
  // Most recent API calls, oldest first; consumers track the last seq they handled.
  events: ApiEvent[]
}

export function useResourceGraph(url = wsUrl()): ResourceGraphState {
  const [graph, setGraph] = useState<ResourceGraph | null>(null)
  const [open, setOpen] = useState<boolean | null>(null) // null until the first connection attempt settles
  const [events, setEvents] = useState<ApiEvent[]>([])
  useEffect(
    () =>
      connectGraph(url, {
        onGraph: setGraph,
        onApiEvent: (e) => setEvents((es) => [...es.slice(-(MAX_EVENTS - 1)), e]),
        onOpenChange: setOpen,
      }),
    [url],
  )
  const state: ConnectionState =
    open === null ? 'connecting' : !open ? 'disconnected' : graph?.status === 'emulator-down' ? 'emulator-down' : graph ? 'live' : 'connecting'
  return { graph, state, events }
}
