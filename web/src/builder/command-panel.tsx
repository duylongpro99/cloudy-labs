// The command an op becomes, exactly as it runs (PRD F4.4), and what happened when it ran:
// exit code, stdout and stderr verbatim, then whether the collector has shown the result (F4.5).
import { useEffect, useState, type CSSProperties } from 'react'
import type { Theme } from '../scene/theme'
import { previewCurrent, type BuilderState } from './use-builder'

type Open = Exclude<BuilderState, { phase: 'idle' | 'dragging' | 'connecting' }>

const STATUS: Record<Open['phase'], string> = {
  form: '',
  running: 'Đang chạy lệnh…',
  waiting: 'Lệnh xong; đang chờ collector thấy thay đổi trong cảnh…',
  done: 'Xong: cảnh đã có thay đổi',
  failed: '',
}

export function CommandPanel({ state, canRun, runBlocker, theme, onRun, onRetry }: { state: Open; canRun: boolean; runBlocker: string | null; theme: Theme; onRun: () => void; onRetry: () => void }) {
  const preview = state.preview
  const command = preview?.command ?? ''
  const blocked = (preview?.problems.length ?? 0) > 0
  // After an edit, the old command stays visible (dimmed) until the new preview arrives.
  const stale = state.phase === 'form' && preview !== null && !previewCurrent(state)
  const [copied, setCopied] = useState(false)
  useEffect(() => setCopied(false), [command])
  const outcome = state.phase === 'waiting' || state.phase === 'done' || state.phase === 'failed' ? state.outcome : null
  const pre: CSSProperties = { margin: '4px 0 0', padding: 8, borderRadius: 6, background: 'rgba(127,127,127,.12)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12, maxHeight: 180, overflow: 'auto' }
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
          disabled={!command || stale}
          onClick={() => void navigator.clipboard?.writeText(command).then(() => setCopied(true), () => setCopied(false))}
        >
          {copied ? 'Đã chép' : 'Chép lệnh'}
        </button>
        {state.phase === 'failed' ? (
          <button id="retry-command" onClick={onRetry}>
            Sửa và chạy lại
          </button>
        ) : (
          <button id="run-command" disabled={state.phase !== 'form' || !preview || stale || blocked || !canRun} onClick={onRun}>
            Run
          </button>
        )}
      </div>
      {!canRun && (
        <p style={{ margin: '6px 0 0', fontSize: 12 }}>
          Nút Run tắt: {runBlocker ?? 'máy chạy lab-server không chạy được lệnh'}. Chép lệnh để xem, nhưng sửa điều trên trước khi chạy.
        </p>
      )}
      {status && (
        <p id="builder-status" role="status" style={{ margin: '6px 0 0', fontWeight: 600, color: state.phase === 'failed' || state.phase === 'form' ? theme.edges.usesKey : undefined }}>
          {status}
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
