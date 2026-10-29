// The builder's state machine (PRD F4.2–F4.6):
//   idle → dragging | connecting → form → running → waiting → done
//                                     ↘ failed (refused, command error, or the scene never showed it)
// Nothing changes in the scene on drop or on Run: the panel waits until the collector's next
// graph shows the expected resource or edge (F4.5), and gives up after WAIT_MS.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { ResourceGraph } from '../graph/types'
import { BuilderError, previewOp, runOp, type Expect, type OpSpec, type Preview, type RunOutcome } from './builder-api'
import type { Draft } from './form-model'

export const PREVIEW_DEBOUNCE_MS = 200
export const WAIT_MS = 5000

export type BuilderState =
  | { phase: 'idle'; notice?: string } // notice: why the last drop or connection went nowhere
  | { phase: 'dragging'; kind: string; op: OpSpec; hover: string | null; reason: string | null }
  | { phase: 'connecting'; source: string; hover: string | null; reason: string | null }
  | { phase: 'form'; draft: Draft; preview: Preview | null; previewRev: number | null; error: string | null } // previewRev: the draft rev the preview was built from
  | { phase: 'running'; draft: Draft; preview: Preview }
  | { phase: 'waiting'; draft: Draft; preview: Preview; outcome: RunOutcome; since: number }
  | { phase: 'done'; draft: Draft; preview: Preview; outcome: RunOutcome }
  | { phase: 'failed'; draft: Draft; preview: Preview | null; outcome: RunOutcome | null; message: string }

export type BuilderAction =
  | { type: 'drag'; kind: string; op: OpSpec }
  | { type: 'connect'; source: string }
  | { type: 'hover'; hover: string | null; reason: string | null }
  | { type: 'drop'; draft: Draft | null; reason: string | null } // null draft: dropped where it cannot go
  | { type: 'open'; draft: Draft }
  | { type: 'edit'; field: string; value: string }
  | { type: 'previewed'; rev: number; preview: Preview | null; error: string | null }
  | { type: 'run' }
  | { type: 'ran'; outcome: RunOutcome; graph: ResourceGraph | null; now: number }
  | { type: 'refused'; error: BuilderError }
  | { type: 'graph'; graph: ResourceGraph }
  | { type: 'tick'; now: number }
  | { type: 'cancel' }

export const IDLE: BuilderState = { phase: 'idle' }

// Whether the graph shows what a run was expected to make.
export function expectMet(expect: Expect, graph: ResourceGraph): boolean {
  if ('after' in expect) return graph.version > expect.after
  if ('edge' in expect) return graph.edges.some((e) => e.id === expect.edge)
  const node = graph.nodes.find((n) => n.id === expect.node)
  if (!node) return false
  return expect.prop === undefined || node.props[expect.prop] === expect.value
}

export const busy = (s: BuilderState) => s.phase === 'running' || s.phase === 'waiting'
const formOf = (draft: Draft): BuilderState => ({ phase: 'form', draft, preview: null, previewRev: null, error: null })

// The preview shows the command for the draft as it is now. Until it does, the panel must not offer
// to run or copy it: the command shown is always the one that would run (F4.4).
export const previewCurrent = (s: BuilderState): boolean =>
  s.phase === 'form' && s.preview !== null && s.previewRev === s.draft.rev
const runnable = (s: BuilderState): boolean => previewCurrent(s) && s.phase === 'form' && s.preview!.problems.length === 0

export function reduce(s: BuilderState, a: BuilderAction): BuilderState {
  switch (a.type) {
    // A new gesture replaces an open form, but never a command that is running or awaited.
    case 'drag':
      return busy(s) ? s : { phase: 'dragging', kind: a.kind, op: a.op, hover: null, reason: null }
    case 'connect':
      return busy(s) ? s : { phase: 'connecting', source: a.source, hover: null, reason: null }
    case 'hover':
      return s.phase === 'dragging' || s.phase === 'connecting' ? { ...s, hover: a.hover, reason: a.reason } : s
    case 'drop':
      if (s.phase !== 'dragging' && s.phase !== 'connecting') return s
      return a.draft ? formOf(a.draft) : a.reason ? { phase: 'idle', notice: a.reason } : IDLE
    case 'open':
      return busy(s) ? s : formOf(a.draft)
    case 'edit': {
      if (s.phase !== 'form' && s.phase !== 'failed') return s
      if (s.draft.locked.includes(a.field)) return s
      const draft = { ...s.draft, params: { ...s.draft.params, [a.field]: a.value }, rev: s.draft.rev + 1 }
      return { phase: 'form', draft, preview: s.preview, previewRev: s.phase === 'form' ? s.previewRev : null, error: null }
    }
    case 'previewed':
      if (s.phase !== 'form' || a.rev !== s.draft.rev) return s
      return { ...s, preview: a.preview, previewRev: a.rev, error: a.error }
    case 'run':
      if (s.phase !== 'form' || !s.preview || !runnable(s)) return s
      return { phase: 'running', draft: s.draft, preview: s.preview }
    case 'ran': {
      if (s.phase !== 'running') return s
      const { draft, preview } = s
      const o = a.outcome
      if (o.exitCode !== 0) {
        const message = o.exitCode === null ? 'Lệnh không trả lời và đã bị dừng' : `Lệnh lỗi (exit code ${o.exitCode}); đọc stderr bên dưới`
        return { phase: 'failed', draft, preview, outcome: o, message }
      }
      if (!o.expect || (a.graph && expectMet(o.expect, a.graph))) return { phase: 'done', draft, preview, outcome: o }
      return { phase: 'waiting', draft, preview, outcome: o, since: a.now }
    }
    case 'refused':
      if (s.phase !== 'running') return s
      return { phase: 'failed', draft: s.draft, preview: { ...s.preview, problems: a.error.problems }, outcome: null, message: a.error.message }
    case 'graph':
      if (s.phase !== 'waiting' || !s.outcome.expect || !expectMet(s.outcome.expect, a.graph)) return s
      return { phase: 'done', draft: s.draft, preview: s.preview, outcome: s.outcome }
    case 'tick':
      if (s.phase !== 'waiting' || a.now - s.since < WAIT_MS) return s
      return {
        phase: 'failed',
        draft: s.draft,
        preview: s.preview,
        outcome: s.outcome,
        message: `Lệnh đã chạy xong nhưng sau ${WAIT_MS / 1000} giây collector vẫn chưa thấy thay đổi trong cảnh; thử Vừa khung hoặc kiểm lại bằng aws CLI`,
      }
    case 'cancel':
      return busy(s) ? s : IDLE
  }
}

export interface Builder {
  state: BuilderState
  dispatch: (a: BuilderAction) => void
  run: () => void
}

export function useBuilder(graph: ResourceGraph | null): Builder {
  const [state, dispatch] = useReducer(reduce, IDLE)
  const graphRef = useRef(graph)
  graphRef.current = graph

  // Preview each form change once the learner pauses typing.
  const draft = state.phase === 'form' ? state.draft : null
  useEffect(() => {
    if (!draft) return
    let live = true
    const timer = setTimeout(() => {
      previewOp(draft.op.name, draft.params).then(
        (preview) => live && dispatch({ type: 'previewed', rev: draft.rev, preview, error: null }),
        (e: unknown) => live && dispatch({ type: 'previewed', rev: draft.rev, preview: null, error: e instanceof Error ? e.message : String(e) }),
      )
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [draft])

  useEffect(() => {
    if (graph) dispatch({ type: 'graph', graph })
  }, [graph])

  const waiting = state.phase === 'waiting'
  useEffect(() => {
    if (!waiting) return
    const timer = setTimeout(() => dispatch({ type: 'tick', now: Date.now() }), WAIT_MS)
    return () => clearTimeout(timer)
  }, [waiting])

  // Esc cancels a drag, a connection or an open form, never a command already running.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && dispatch({ type: 'cancel' })
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const stateRef = useRef(state)
  stateRef.current = state
  const run = useCallback(() => {
    const s = stateRef.current
    if (!runnable(s) || s.phase !== 'form') return
    dispatch({ type: 'run' })
    runOp(s.draft.op.name, s.draft.params).then(
      (outcome) => dispatch({ type: 'ran', outcome, graph: graphRef.current, now: Date.now() }),
      (e: unknown) => dispatch({ type: 'refused', error: e instanceof BuilderError ? e : new BuilderError(String(e), 0) }),
    )
  }, [])

  return { state, dispatch, run }
}
