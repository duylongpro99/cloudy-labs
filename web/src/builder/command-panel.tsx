// The command an op becomes, exactly as it runs (PRD F4.4), and what happened when it ran:
// exit code, stdout and stderr verbatim, then whether the collector has shown the result (F4.5).
// In practice mode (F4.7) there is no Run: copying the command hands it to the learner's terminal.
import { useEffect, useState, type CSSProperties } from 'react'
import type { ApiEvent } from '../graph/types'
import type { Theme } from '../scene/theme'
import type { RunOutcome } from './builder-api'
import { previewCurrent, type BuilderState } from './use-builder'

type Open = Exclude<BuilderState, { phase: 'idle' | 'dragging' | 'connecting' }>

const STATUS: Record<Open['phase'], string> = {
  form: '',
  running: 'Đang chạy lệnh…',
  waiting: 'Lệnh xong; đang chờ collector thấy thay đổi trong cảnh…',
  practicing: 'Dán lệnh vào terminal và chạy; cảnh sẽ tự cập nhật',
  done: 'Xong: cảnh đã có thay đổi',
  failed: '',
}

// The private key create-key-pair printed, the only time AWS ever shows it. It stays in this
// page's memory only: never in localStorage, never sent anywhere.
export function pemOf(op: string, outcome: RunOutcome | null): { name: string; key: string } | null {
  if (op !== 'create-key-pair' || outcome?.exitCode !== 0) return null
  try {
    const out = JSON.parse(outcome.stdout) as { KeyName?: unknown; KeyMaterial?: unknown }
    return typeof out.KeyMaterial === 'string' && out.KeyMaterial ? { name: String(out.KeyName ?? 'key'), key: out.KeyMaterial } : null
  } catch {
    return null
  }
}

export const NAME_HINT_MS = 10_000

// The API action a CLI op calls: run-instances → RunInstances.
export const actionOf = (op: string) => op.replace(/(^|-)(\w)/g, (_, _dash: string, c: string) => c.toUpperCase())

// The newest state-changing call the emulator saw since the command was copied.
export function lastWrite(events: ApiEvent[], since: number): ApiEvent | null {
  return events.findLast((e) => e.write && e.seq > since) ?? null
}

// Once the learner's own call reached the emulator, give the collector NAME_HINT_MS to show it;
// if it still has not, the name typed in the terminal most likely differs from the form's.
function useNameHint(state: Open, events: ApiEvent[]): boolean {
  const since = state.phase === 'practicing' ? state.since : null
  const arrived = since !== null && events.some((e) => e.write && e.seq > since && e.action === actionOf(state.draft.op.name))
  const [late, setLate] = useState(false)
  useEffect(() => {
    setLate(false)
    if (!arrived) return
    const timer = setTimeout(() => setLate(true), NAME_HINT_MS)
    return () => clearTimeout(timer)
  }, [arrived, since])
  return arrived && late
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/x-pem-file' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 60_000) // some browsers start reading the blob after click() returns
}

export function CommandPanel({ state, canRun, runBlocker, practice, events, theme, onRun, onPractice, onRetry, chatBusy = false }: {
  state: Open
  canRun: boolean
  runBlocker: string | null
  practice: boolean
  events: ApiEvent[]
  theme: Theme
  onRun: () => void
  onPractice: () => void
  onRetry: () => void
  chatBusy?: boolean
}) {
  const preview = state.preview
  const command = preview?.command ?? ''
  const blocked = (preview?.problems.length ?? 0) > 0
  // After an edit, the old command stays visible (dimmed) until the new preview arrives.
  const stale = state.phase === 'form' && preview !== null && !previewCurrent(state)
  const [copied, setCopied] = useState(false)
  useEffect(() => setCopied(false), [command])
  const outcome = state.phase === 'waiting' || state.phase === 'done' || state.phase === 'failed' ? state.outcome : null
  const pre: CSSProperties = { margin: '4px 0 0', padding: 8, borderRadius: 6, background: 'rgba(127,127,127,.12)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12, maxHeight: 180, overflow: 'auto' }
  const pem = pemOf(state.draft.op.name, outcome)
  const seen = state.phase === 'practicing' ? lastWrite(events, state.since) : null
  const nameHint = useNameHint(state, events)
  const status = state.phase === 'failed' ? state.message : state.phase === 'form' && state.error ? state.error : STATUS[state.phase]

  return (
    <section id="command-panel" data-phase={state.phase}>
      <div style={{ opacity: 0.75, fontSize: 12 }}>Lệnh sẽ chạy</div>
      <pre id="builder-command" data-stale={stale} style={stale ? { ...pre, opacity: 0.45 } : pre}>
        {command || (state.phase === 'form' && !state.error ? 'Đang dựng lệnh…' : '')}
      </pre>
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        <button
          id="copy-command"
          disabled={!command || stale || blocked}
          onClick={() => {
            void navigator.clipboard?.writeText(command).then(() => setCopied(true), () => setCopied(false))
            if (practice) onPractice()
          }}
        >
          {copied ? 'Đã chép' : 'Chép lệnh'}
        </button>
        {practice ? null : state.phase === 'failed' ? (
          <button id="retry-command" onClick={onRetry}>
            Sửa và chạy lại
          </button>
        ) : (
          <button id="run-command" disabled={state.phase !== 'form' || !preview || stale || blocked || !canRun || chatBusy} onClick={onRun}>
            Run
          </button>
        )}
      </div>
      {chatBusy && !practice && <p id="chat-busy-note" style={{ margin: '6px 0 0', fontSize: 12 }}>Trợ lý lệnh đang chạy một bước; chờ nó xong rồi Run.</p>}
      {!canRun && !practice && (
        <p style={{ margin: '6px 0 0', fontSize: 12 }}>
          Nút Run tắt: {runBlocker ?? 'máy chạy lab-server không chạy được lệnh'}. Chép lệnh để xem, nhưng sửa điều trên trước khi chạy.
        </p>
      )}
      {status && (
        <p id="builder-status" role="status" style={{ margin: '6px 0 0', fontWeight: 600, color: state.phase === 'failed' || state.phase === 'form' ? theme.edges.usesKey : undefined }}>
          {status}
        </p>
      )}
      {state.phase === 'practicing' && (
        <p id="practice-seen" style={{ margin: '6px 0 0', fontSize: 12 }}>
          {seen ? (
            <>
              Emulator vừa nhận: <code>{seen.service} {seen.action}</code>
            </>
          ) : (
            'Emulator chưa nhận lệnh ghi nào kể từ lúc chép.'
          )}
        </p>
      )}
      {nameHint && (
        <p id="practice-name-hint" style={{ margin: '6px 0 0', fontSize: 12, color: theme.edges.usesKey }}>
          Emulator đã nhận {actionOf(state.draft.op.name)} nhưng cảnh vẫn chưa có kết quả. Kiểm lại tên (Name tag) và các id đã gõ trong
          terminal có giống lệnh trên không.
        </p>
      )}
      {pem && (
        <p id="pem-download" style={{ margin: '6px 0 0', fontSize: 12 }}>
          <button id="download-pem" onClick={() => download(`${pem.name}.pem`, pem.key)}>
            Tải {pem.name}.pem
          </button>{' '}
          AWS chỉ trả private key một lần, ngay bây giờ. Sau khi tải, chạy <code>chmod 400 {pem.name}.pem</code> để ssh chịu dùng nó.
        </p>
      )}
      {outcome && (
        <div id="command-output" style={{ marginTop: 6 }}>
          <div>
            exit code <code id="exit-code">{outcome.exitCode ?? 'không có (đã dừng)'}</code> · {outcome.durationMs} ms
          </div>
          {outcome.stdout && (
            <>
              <div style={{ opacity: 0.75, fontSize: 12, marginTop: 4 }}>stdout</div>
              <pre id="command-stdout" style={pre}>{outcome.stdout}</pre>
            </>
          )}
          {outcome.stderr && (
            <>
              <div style={{ opacity: 0.75, fontSize: 12, marginTop: 4 }}>stderr</div>
              <pre id="command-stderr" style={pre}>{outcome.stderr}</pre>
            </>
          )}
        </div>
      )}
    </section>
  )
}
