// The chat's state (PRD F5): the conversation, and how each step of the latest answer is run.
// A step runs the way a builder op does: preview with the ids filled in, Run, then wait until the
// collector's next graph shows the result (F4.5). A step that uses an earlier step's id `{ref: n}`
// can only run once step n is done and its id is known.
//   pending → resolving → running → waiting → done(id)
//                ↘ practicing → done(id) (practice mode, F4.7: the learner runs the command)
//                ↘ failed (blocked, refused, command error, or the scene never showed it)
// The history lives in the page only, and is dropped when the lab or its attempt changes: the ids
// it names are gone after a reset.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { BuilderError, previewOp, runOp, type Expect, type LabInfo, type Params, type PracticeExpect, type Problem, type RunOutcome } from '../builder/builder-api'
import { WAIT_MS, expectMet, practiceMet } from '../builder/use-builder'
import type { ResourceGraph } from '../graph/types'
import { CHAT_TURNS_MAX, CHAT_TURN_CHARS_MAX, sendChat, type ChatMessage, type ChatReply, type ChatStep } from './chat-api'

export type StepRun =
  | { status: 'pending' }
  | { status: 'resolving' } // previewing the command with the earlier steps' ids filled in
  | { status: 'running'; command: string }
  | { status: 'waiting'; command: string; expect: Expect; since: number }
  // known: the node ids the graph had when the command was handed over
  | { status: 'practicing'; command: string; expect: PracticeExpect; known: string[] }
  | { status: 'done'; command: string; id?: string } // id: the resource a create step made
  | { status: 'failed'; command?: string; message: string; problems: Problem[] }

export type ChatTurn = { role: 'user'; text: string } | { role: 'assistant'; reply: ChatReply }

export interface ChatState {
  turns: ChatTurn[]
  asking: boolean
  error: string | null
  runs: StepRun[] // one per step of the latest answer
  chain: boolean // "Run cả chuỗi" is going
}

export type ChatAction =
  | { type: 'reset' }
  | { type: 'ask'; text: string }
  | { type: 'answered'; reply: ChatReply }
  | { type: 'ask-failed'; message: string }
  | { type: 'resolving'; step: number }
  | { type: 'blocked'; step: number; message: string; problems?: Problem[]; command?: string }
  | { type: 'running'; step: number; command: string }
  | { type: 'ran'; step: number; outcome: RunOutcome; graph: ResourceGraph | null; now: number }
  | { type: 'practicing'; step: number; command: string; expect: PracticeExpect; known: string[] }
  | { type: 'graph'; graph: ResourceGraph }
  | { type: 'tick'; now: number }
  | { type: 'chain' }
  | { type: 'stop' }

export const EMPTY: ChatState = { turns: [], asking: false, error: null, runs: [], chain: false }

export const lastReply = (s: ChatState): ChatReply | null => {
  const last = s.turns.at(-1)
  return last?.role === 'assistant' ? last.reply : null
}

// A step is in flight from its preview until the scene shows it; practice waits on the learner.
const inFlight = (r: StepRun) => r.status === 'resolving' || r.status === 'running' || r.status === 'waiting'

export const stepBusy = (s: ChatState) => s.chain || s.runs.some(inFlight)

export const runnable = (r: StepRun) => r.status === 'pending' || r.status === 'failed'

// The step's params with each `{ref: n}` replaced by the id step n made, or why it cannot run yet.
export function resolveParams(step: ChatStep, runs: readonly StepRun[]): Params | string {
  const out: Params = {}
  for (const [name, value] of Object.entries(step.params)) {
    if (typeof value === 'string') {
      out[name] = value
      continue
    }
    const run = runs[value.ref - 1]
    if (run?.status !== 'done') return `Chạy bước ${value.ref} trước: bước này dùng id bước đó tạo`
    if (!run.id) return `Bước ${value.ref} không cho id để điền vào ${name}`
    out[name] = run.id
  }
  return out
}

// The id of the resource a run made, as the graph shows it.
function madeId(expect: PracticeExpect, graph: ResourceGraph, known: readonly string[] = []): string | undefined {
  if ('node' in expect) return expect.node
  if (!('kind' in expect)) return undefined
  const kinds = expect.kind === 'subnet' ? ['subnet-public', 'subnet-private'] : [expect.kind]
  return graph.nodes.find((n) => kinds.includes(n.kind) && n.label === expect.label && !known.includes(n.id))?.id
}

// What the server is sent: the latest turns, an answer as its words and the ops it suggested.
export function history(turns: readonly ChatTurn[]): ChatMessage[] {
  const latest = turns.slice(-CHAT_TURNS_MAX)
  return latest.slice(latest[0]?.role === 'assistant' ? 1 : 0).map((t) => {
    if (t.role === 'user') return { role: 'user', content: t.text.slice(0, CHAT_TURN_CHARS_MAX) }
    const { reply, refusal, steps } = t.reply
    const parts = [reply.trim(), refusal && `Ngoài phạm vi: ${refusal}`, steps.length > 0 && `Các bước: ${steps.map((s) => s.op).join(', ')}`]
    const content = parts.filter(Boolean).join('\n') || '(không có bước nào)'
    return { role: 'assistant', content: content.slice(0, CHAT_TURN_CHARS_MAX) }
  })
}

function setRun(s: ChatState, step: number, run: StepRun): ChatState {
  return { ...s, runs: s.runs.map((r, i) => (i === step ? run : r)) }
}

export function reduce(s: ChatState, a: ChatAction): ChatState {
  switch (a.type) {
    case 'reset':
      return EMPTY
    case 'ask':
      if (s.asking || stepBusy(s)) return s
      return { ...s, turns: [...s.turns, { role: 'user', text: a.text }], asking: true, error: null }
    case 'answered':
      if (!s.asking) return s
      return { ...s, turns: [...s.turns, { role: 'assistant', reply: a.reply }], asking: false, runs: a.reply.steps.map(() => ({ status: 'pending' })), chain: false }
    case 'ask-failed':
      return s.asking ? { ...s, asking: false, error: a.message } : s
    case 'resolving':
      return runnable(s.runs[a.step] ?? { status: 'done', command: '' }) ? setRun(s, a.step, { status: 'resolving' }) : s
    case 'blocked': {
      const r = s.runs[a.step]
      if (!r || !(runnable(r) || r.status === 'resolving' || r.status === 'running')) return s
      const command = a.command ?? (r.status === 'running' ? r.command : undefined)
      return setRun(s, a.step, { status: 'failed', command, message: a.message, problems: a.problems ?? [] })
    }
    case 'running':
      return s.runs[a.step]?.status === 'resolving' ? setRun(s, a.step, { status: 'running', command: a.command }) : s
    case 'practicing':
      if (s.runs[a.step]?.status !== 'resolving') return s
      return setRun(s, a.step, { status: 'practicing', command: a.command, expect: a.expect, known: a.known })
    case 'ran': {
      const r = s.runs[a.step]
      if (r?.status !== 'running') return s
      const o = a.outcome
      if (o.exitCode !== 0) {
        const message = o.exitCode === null ? 'Lệnh không trả lời và đã bị dừng' : `Lệnh lỗi (exit code ${o.exitCode}): ${o.stderr.trim().slice(0, 500)}`
        return setRun(s, a.step, { status: 'failed', command: r.command, message, problems: [] })
      }
      if (!o.expect) return setRun(s, a.step, { status: 'done', command: r.command })
      if (a.graph && expectMet(o.expect, a.graph)) return setRun(s, a.step, { status: 'done', command: r.command, id: madeId(o.expect, a.graph) })
      return setRun(s, a.step, { status: 'waiting', command: r.command, expect: o.expect, since: a.now })
    }
    case 'graph': {
      const runs = s.runs.map((r): StepRun => {
        if (r.status === 'waiting' && expectMet(r.expect, a.graph)) return { status: 'done', command: r.command, id: madeId(r.expect, a.graph) }
        if (r.status === 'practicing' && practiceMet(r.expect, a.graph, r.known)) return { status: 'done', command: r.command, id: madeId(r.expect, a.graph, r.known) }
        return r
      })
      return runs.some((r, i) => r !== s.runs[i]) ? { ...s, runs } : s
    }
    case 'tick': {
      const late = (r: StepRun) => r.status === 'waiting' && a.now - r.since >= WAIT_MS
      if (!s.runs.some(late)) return s
      const message = `Lệnh đã chạy xong nhưng sau ${WAIT_MS / 1000} giây collector vẫn chưa thấy thay đổi trong cảnh; kiểm lại bằng aws CLI`
      return { ...s, runs: s.runs.map((r): StepRun => (late(r) && r.status === 'waiting' ? { status: 'failed', command: r.command, message, problems: [] } : r)) }
    }
    case 'chain':
      if (stepBusy(s) || s.runs.length === 0) return s
      // Start again from the first step not done, including one that failed before.
      return { ...s, chain: true, runs: s.runs.map((r): StepRun => (r.status === 'failed' ? { status: 'pending' } : r)) }
    case 'stop':
      return s.chain ? { ...s, chain: false } : s
  }
}

export interface Chat {
  state: ChatState
  ask: (text: string) => void
  run: (step: number) => void
  runAll: () => void
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e))

// Why a preview or run request failed, with the server's problems when it sent any.
const failure = (e: unknown) => ({ message: messageOf(e), problems: e instanceof BuilderError ? e.problems : [] })

export function useChat(graph: ResourceGraph | null, lab: LabInfo | null, practice: boolean): Chat {
  const [state, dispatch] = useReducer(reduce, EMPTY)
  const stateRef = useRef(state)
  stateRef.current = state
  const graphRef = useRef(graph)
  graphRef.current = graph
  const practiceRef = useRef(practice)
  practiceRef.current = practice

  // Answers and runs started before a reset belong to the old lab: drop them when they land.
  const gen = useRef(0)
  const labKey = lab ? `${lab.id}:${lab.attempt}` : null
  useEffect(() => {
    gen.current += 1
    dispatch({ type: 'reset' })
  }, [labKey])
  const sender = useCallback(() => {
    const mine = gen.current
    const send = (a: ChatAction) => mine === gen.current && dispatch(a)
    send.stale = () => mine !== gen.current
    return send
  }, [])

  useEffect(() => {
    if (graph) dispatch({ type: 'graph', graph })
  }, [graph])

  const waiting = state.runs.some((r) => r.status === 'waiting')
  useEffect(() => {
    if (!waiting) return
    const timer = setTimeout(() => dispatch({ type: 'tick', now: Date.now() }), WAIT_MS)
    return () => clearTimeout(timer)
  }, [waiting])

  const ask = useCallback(
    (text: string) => {
      const s = stateRef.current
      if (!text.trim() || s.asking || stepBusy(s)) return
      const send = sender()
      const turns: ChatTurn[] = [...s.turns, { role: 'user', text }]
      dispatch({ type: 'ask', text })
      sendChat(history(turns)).then(
        (reply) => send({ type: 'answered', reply }),
        (e: unknown) => send({ type: 'ask-failed', message: messageOf(e) }),
      )
    },
    [sender],
  )

  const start = useCallback(
    async (i: number, inChain: boolean) => {
      const s = stateRef.current
      const step = lastReply(s)?.steps[i]
      const r = s.runs[i]
      if (!step || !r || !runnable(r) || (s.chain && !inChain) || (!inChain && stepBusy(s))) return
      const send = sender()
      if (step.problems.length > 0) return send({ type: 'blocked', step: i, message: 'Bước này có lỗi; hỏi lại để model sửa', problems: step.problems })
      const params = resolveParams(step, s.runs)
      if (typeof params === 'string') return send({ type: 'blocked', step: i, message: params })
      // Marked before the first await, so the chain sees this step in flight and starts nothing else.
      stateRef.current = reduce(s, { type: 'resolving', step: i })
      send({ type: 'resolving', step: i })
      let command: string
      try {
        const preview = await previewOp(step.op, params)
        command = preview.command
        if (preview.problems.length > 0) return send({ type: 'blocked', step: i, message: 'Lệnh chưa chạy được với cảnh hiện tại', problems: preview.problems, command })
        if (practiceRef.current) {
          void navigator.clipboard?.writeText(command).catch(() => {})
          return send({ type: 'practicing', step: i, command, expect: preview.practiceExpect, known: graphRef.current?.nodes.map((n) => n.id) ?? [] })
        }
      } catch (e) {
        return send({ type: 'blocked', step: i, ...failure(e) })
      }
      if (send.stale()) return // the lab was reset while the preview was out: this answer belongs to the old attempt
      send({ type: 'running', step: i, command })
      try {
        const outcome = await runOp(step.op, params)
        send({ type: 'ran', step: i, outcome, graph: graphRef.current, now: Date.now() })
      } catch (e) {
        send({ type: 'blocked', step: i, ...failure(e) })
      }
    },
    [sender],
  )

  // Run cả chuỗi: once nothing is in flight, start the first step not done; stop at a failure.
  useEffect(() => {
    if (!state.chain || state.runs.some(inFlight)) return
    const next = state.runs.findIndex((r) => r.status !== 'done')
    if (next === -1 || state.runs[next].status !== 'pending') dispatch({ type: 'stop' })
    else void start(next, true)
  }, [state, start])

  const run = useCallback((i: number) => void start(i, false), [start])
  const runAll = useCallback(() => dispatch({ type: 'chain' }), [])
  return { state, ask, run, runAll }
}
