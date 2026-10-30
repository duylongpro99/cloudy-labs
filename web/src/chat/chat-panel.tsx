// The chat panel (PRD F5): the learner asks in their own words and gets builder steps, each with
// its command, why it is there and what the server found wrong with it. Nothing runs until the
// learner presses Run on a step or "Run cả chuỗi"; in practice mode the command is copied instead.
import { useState, type CSSProperties } from 'react'
import type { LabInfo, Problem } from '../builder/builder-api'
import { OP_TITLE } from '../builder/builder-panel'
import type { Theme } from '../scene/theme'
import { CHAT_TURN_CHARS_MAX, type ChatReply, type ChatStep } from './chat-api'
import { runnable, stepBusy, type Chat, type StepRun } from './use-chat'

const ENV_VARS = ['LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_API_FORMAT']

const STATUS: Record<StepRun['status'], string> = {
  pending: '',
  resolving: 'Đang dựng lệnh…',
  running: 'Đang chạy…',
  waiting: 'Đã chạy, chờ cảnh cập nhật…',
  practicing: 'Đã chép lệnh; chạy nó trong terminal, cảnh sẽ tự cập nhật',
  done: 'Xong',
  failed: '',
}

const pre: CSSProperties = { margin: '4px 0 0', padding: 8, borderRadius: 6, background: 'rgba(127,127,127,.12)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12, maxHeight: 160, overflow: 'auto' }

function Problems({ problems, color }: { problems: Problem[]; color: string }) {
  if (problems.length === 0) return null
  return (
    <ul className="step-problems" style={{ margin: '4px 0 0', paddingLeft: 18, color, fontSize: 12 }}>
      {problems.map((p) => (
        <li key={`${p.field}:${p.message}`}>{p.field ? `${p.field}: ${p.message}` : p.message}</li>
      ))}
    </ul>
  )
}

function Step({ n, step, run, practice, canRun, locked, warn, onRun }: {
  n: number
  step: ChatStep
  run: StepRun | null // null: a step of an earlier answer, shown but no longer run from here
  practice: boolean
  canRun: boolean
  locked: boolean
  warn: string
  onRun: () => void
}) {
  const command = run && 'command' in run && run.command ? run.command : step.command
  const problems = run?.status === 'failed' && run.problems.length > 0 ? run.problems : step.problems
  const disabled = locked || step.problems.length > 0 || !run || !runnable(run) || (!practice && !canRun)
  return (
    <li className="chat-step" data-status={run?.status ?? 'past'} style={{ margin: '8px 0 0' }}>
      <div>
        <b>Bước {n}:</b> {OP_TITLE[step.op] ?? step.op}
        {step.deferred && run?.status !== 'done' && (
          <span className="step-deferred" title="Bước này dùng id bước trước tạo; lab-server kiểm nó khi chạy" style={{ marginLeft: 6, fontSize: 11, opacity: 0.75 }}>
            kiểm khi chạy
          </span>
        )}
      </div>
      {step.explanation && <div style={{ fontSize: 12, opacity: 0.85 }}>{step.explanation}</div>}
      {command && <pre className="step-command" style={pre}>{command}</pre>}
      <Problems problems={problems} color={warn} />
      {run && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
          <button className="run-step" disabled={disabled} onClick={onRun}>
            {practice ? 'Chép' : run.status === 'failed' ? 'Chạy lại' : 'Run'}
          </button>
          <span className="step-status" role="status" style={{ fontSize: 12, color: run.status === 'failed' ? warn : undefined }}>
            {run.status === 'failed' ? run.message : run.status === 'done' && run.id ? `Xong: ${run.id}` : STATUS[run.status]}
          </span>
        </div>
      )}
    </li>
  )
}

function Answer({ reply, runs, practice, canRun, locked, warn, onRun }: {
  reply: ChatReply
  runs: StepRun[] | null // null: an earlier answer
  practice: boolean
  canRun: boolean
  locked: boolean
  warn: string
  onRun: (i: number) => void
}) {
  return (
    <div className="chat-answer">
      {reply.refusal && (
        <p className="chat-refusal" style={{ margin: 0 }}>
          <b style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4, background: 'rgba(127,127,127,.2)' }}>Ngoài phạm vi</b> {reply.refusal}
        </p>
      )}
      {reply.reply && <p style={{ margin: reply.refusal ? '4px 0 0' : 0, whiteSpace: 'pre-wrap' }}>{reply.reply}</p>}
      {reply.steps.length > 0 && (
        <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
          {reply.steps.map((step, i) => (
            <Step key={i} n={i + 1} step={step} run={runs?.[i] ?? null} practice={practice} canRun={canRun} locked={locked} warn={warn} onRun={() => onRun(i)} />
          ))}
        </ol>
      )}
    </div>
  )
}

function CodeList({ names }: { names: string[] }) {
  return names.map((v, i) => <span key={v}>{i > 0 && ', '}<code>{v}</code></span>)
}

function Setup({ lab }: { lab: LabInfo }) {
  const missing = lab.chat.enabled ? [] : lab.chat.missing
  return (
    <div id="chat-setup" style={{ fontSize: 12 }}>
      <p style={{ margin: '0 0 6px' }}>
        Chat chưa bật. Đặt <CodeList names={ENV_VARS} /> trong biến môi trường của <code>labctl serve</code> hoặc trong{' '}
        <code>~/.cloudy-labs/llm.env</code>, rồi chạy lại <code>labctl serve</code>.
      </p>
      {missing.length > 0 && (
        <p id="chat-missing" style={{ margin: '0 0 6px' }}>
          Còn thiếu: <CodeList names={missing} />
        </p>
      )}
      {!lab.chat.enabled && lab.chat.error && <p style={{ margin: 0 }}>{lab.chat.error}</p>}
      <p style={{ margin: 0, opacity: 0.8 }}><code>LLM_API_FORMAT</code> là <code>openai</code> hoặc <code>anthropic</code>; xem docs/labctl.md.</p>
    </div>
  )
}

export function ChatPanel({ chat, lab, practice, onPractice, builderBusy, theme }: {
  chat: Chat
  lab: LabInfo
  practice: boolean
  onPractice: (on: boolean) => void
  builderBusy: boolean // the builder is running a command: one command at a time
  theme: Theme
}) {
  const [open, setOpen] = useState(true)
  const [text, setText] = useState('')
  const { state } = chat
  const warn = theme.edges.usesKey
  const latest = state.turns.length - 1
  const busy = stepBusy(state)
  const runs = state.runs
  const canSend = text.trim() !== '' && !state.asking && !busy
  const send = () => {
    if (!canSend) return
    chat.ask(text)
    setText('')
  }
  return (
    <aside
      id="chat-panel"
      aria-label="Trợ lý lệnh"
      style={{
        position: 'fixed',
        bottom: 12, // below the property panel, which opens top right
        right: 12,
        width: open ? 400 : 'auto',
        maxWidth: 'calc(100vw - 24px)',
        maxHeight: '60vh',
        display: 'flex',
        flexDirection: 'column',
        padding: '8px 12px',
        borderRadius: 8,
        background: theme.background,
        color: theme.label,
        boxShadow: '0 1px 4px rgba(0,0,0,.25)',
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ flex: 1 }}>Trợ lý lệnh</b>
        {open && lab.chat.enabled && (
          <label style={{ fontSize: 12 }} title="Không chạy lệnh; bạn tự chạy lệnh đã chép trong terminal">
            <input id="chat-practice" type="checkbox" checked={practice} disabled={busy} onChange={(e) => onPractice(e.target.checked)} /> Luyện tập
          </label>
        )}
        <button id="chat-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'Thu gọn' : 'Mở'}
        </button>
      </div>
      {open && (!lab.chat.enabled ? (
        <div style={{ marginTop: 8 }}>
          <Setup lab={lab} />
        </div>
      ) : (
        <>
          <div id="chat-messages" style={{ overflow: 'auto', flex: 1, marginTop: 8 }}>
            {state.turns.length === 0 && (
              <p style={{ margin: 0, opacity: 0.75, fontSize: 12 }}>
                Hỏi bằng lời của bạn, ví dụ "tạo subnet công khai 10.0.1.0/24 trong VPC của tôi". Trợ lý gợi ý từng bước với lệnh aws; không gì chạy cho tới khi bạn bấm Run.
              </p>
            )}
            {state.turns.map((t, i) =>
              t.role === 'user' ? (
                <p key={i} className="chat-user" style={{ margin: '8px 0 0', padding: '4px 8px', borderRadius: 6, background: 'rgba(127,127,127,.12)', whiteSpace: 'pre-wrap' }}>
                  {t.text}
                </p>
              ) : (
                <div key={i} style={{ marginTop: 8 }}>
                  <Answer
                    reply={t.reply}
                    runs={i === latest ? runs : null}
                    practice={practice}
                    canRun={lab.canRun}
                    locked={busy || builderBusy}
                    warn={warn}
                    onRun={chat.run}
                  />
                </div>
              ),
            )}
            {state.asking && <p id="chat-asking" style={{ margin: '8px 0 0', opacity: 0.75 }}>Đang hỏi model…</p>}
            {state.error && (
              <p id="chat-error" role="alert" style={{ margin: '8px 0 0', color: warn }}>
                {state.error}
              </p>
            )}
          </div>
          {runs.length > 1 && !practice && (
            <button id="run-all" style={{ marginTop: 8 }} disabled={busy || builderBusy || !lab.canRun || runs.every((r) => r.status === 'done')} onClick={chat.runAll}>
              Run cả chuỗi
            </button>
          )}
          {runs.length > 0 && !practice && !lab.canRun && (
            <p style={{ margin: '6px 0 0', fontSize: 12 }}>Nút Run tắt: {lab.runBlocker ?? 'máy chạy lab-server không chạy được lệnh'}.</p>
          )}
          {builderBusy && runs.length > 0 && <p style={{ margin: '6px 0 0', fontSize: 12 }}>Builder đang chạy một lệnh; chờ nó xong.</p>}
          <form
            style={{ display: 'flex', gap: 6, marginTop: 8 }}
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
          >
            <textarea
              id="chat-input"
              aria-label="Câu hỏi"
              rows={2}
              maxLength={CHAT_TURN_CHARS_MAX}
              value={text}
              placeholder="Enter để gửi, Shift+Enter xuống dòng"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  send()
                }
              }}
              style={{ flex: 1, resize: 'vertical', font: 'inherit' }}
            />
            <button id="chat-send" type="submit" disabled={!canSend}>
              Gửi
            </button>
          </form>
        </>
      ))}
    </aside>
  )
}
