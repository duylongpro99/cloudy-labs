// The lab's checks, grouped by task in the lab's order (PRD F6.3). Each shows whether it passed
// against the emulator's current state; pressing one lights up what it looks at in the scene,
// pressing it again (or Esc) lets go.
import type { LabInfo } from '../builder/builder-api'
import type { CheckStatus, TwinCheck, TwinState } from '../graph/types'
import type { Theme } from '../scene/theme'

export const STATUS_TEXT: Record<CheckStatus, string> = { passed: 'Đạt', failed: 'Chưa đạt', pending: 'Đang chờ' }
const STATUS_MARK: Record<CheckStatus, string> = { passed: '✓', failed: '✗', pending: '…' }

export interface TaskGroup {
  id: string
  text: string
  checks: TwinCheck[]
}

// Tasks in the lab's order; a task the lab info does not list (yet) follows, in check order.
export function groupByTask(checks: readonly TwinCheck[], tasks: LabInfo['tasks'] = []): TaskGroup[] {
  const groups = new Map<string, TaskGroup>(tasks.map((t) => [t.id, { id: t.id, text: t.text, checks: [] }]))
  for (const c of checks) {
    if (!groups.has(c.task)) groups.set(c.task, { id: c.task, text: c.task, checks: [] })
    groups.get(c.task)!.checks.push(c)
  }
  return [...groups.values()].filter((g) => g.checks.length > 0)
}

export function CheckPanel({ twin, lab, selected, onSelect, theme }: {
  twin: TwinState
  lab: LabInfo | null
  selected: string | null
  onSelect: (checkId: string | null) => void
  theme: Theme
}) {
  const passed = twin.checks.filter((c) => c.status === 'passed').length
  const colour: Record<CheckStatus, string> = { passed: theme.achieved, failed: theme.failed, pending: theme.ghost.label }
  return (
    // Folds away to the summary line, since the open list covers part of the scene on a small window.
    <details id="check-panel" open aria-label="Kiểm tra" style={{ marginTop: 8 }}>
      <summary style={{ cursor: 'pointer' }}>
        <b>Kiểm tra</b> · <span id="check-summary">{passed}/{twin.checks.length} đạt</span>
      </summary>
      <div style={{ maxHeight: '40vh', overflow: 'auto' }}>
        {groupByTask(twin.checks, lab?.tasks).map((g) => (
          <div key={g.id} className="check-task" data-task={g.id} style={{ marginTop: 6 }}>
            <div style={{ fontSize: 12, opacity: 0.85 }}>{g.text}</div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {g.checks.map((c) => {
                const on = selected === c.id
                return (
                  <li key={c.id} style={{ marginTop: 2 }}>
                    <button
                      className="check-item"
                      data-check={c.id}
                      data-status={c.status}
                      aria-pressed={on}
                      onClick={() => onSelect(on ? null : c.id)}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '4px 6px',
                        borderRadius: 6,
                        border: `1px solid ${on ? theme.outline : 'transparent'}`,
                        background: on ? 'rgba(127,127,127,.15)' : 'transparent',
                        color: 'inherit',
                        font: 'inherit',
                        cursor: 'pointer',
                      }}
                    >
                      <span aria-hidden style={{ color: colour[c.status], fontWeight: 600, marginRight: 6 }}>{STATUS_MARK[c.status]}</span>
                      <span className="check-status" style={{ color: colour[c.status] }}>{STATUS_TEXT[c.status]}</span>
                      {' · '}
                      {c.description || c.id}
                      {c.message && <span className="check-message" style={{ display: 'block', fontSize: 12, opacity: 0.8, marginLeft: 18 }}>{c.message}</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </details>
  )
}
