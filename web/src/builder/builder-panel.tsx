// The builder's side panel: the open op's form above its command, output and status.
import { useState } from 'react'
import type { ApiEvent, ResourceGraph } from '../graph/types'
import type { Theme } from '../scene/theme'
import type { LabInfo } from './builder-api'
import { BuildForm } from './build-form'
import { CommandPanel } from './command-panel'
import type { BuilderAction, BuilderState } from './use-builder'

const OP_TITLE: Record<string, string> = {
  'create-vpc': 'Tạo VPC',
  'create-subnet': 'Tạo subnet',
  'create-internet-gateway': 'Tạo Internet Gateway',
  'attach-internet-gateway': 'Gắn Internet Gateway vào VPC',
  'allocate-address': 'Cấp Elastic IP',
  'create-nat-gateway': 'Tạo NAT Gateway',
  'create-route-table': 'Tạo Route Table',
  'create-route': 'Thêm route',
  'associate-route-table': 'Gắn Route Table vào subnet',
  'modify-vpc-attribute': 'Bật DNS hostnames cho VPC',
  'modify-subnet-attribute': 'Tự gán IP public trong subnet',
  'create-security-group': 'Tạo Security Group',
  'authorize-security-group-ingress': 'Thêm rule inbound',
  'create-key-pair': 'Tạo Key Pair',
  'run-instances': 'Chạy EC2 Instance',
  'modify-instance-attribute': 'Gắn Security Group vào instance',
}

type Open = Exclude<BuilderState, { phase: 'idle' | 'dragging' | 'connecting' }>

const PRACTICE_KEY = 'cloudy-labs:practice'

// A per-browser convenience: storage may be missing or throw (private windows, blocked site data).
function savedPractice(): boolean {
  try {
    return localStorage.getItem(PRACTICE_KEY) === '1'
  } catch {
    return false
  }
}

function savePractice(on: boolean) {
  try {
    localStorage.setItem(PRACTICE_KEY, on ? '1' : '0')
  } catch {
    // the toggle still works for this page
  }
}

export function BuilderPanel({ state, graph, lab, events, theme, dispatch, onRun }: {
  state: Open
  graph: ResourceGraph | null
  lab: LabInfo
  events: ApiEvent[]
  theme: Theme
  dispatch: (a: BuilderAction) => void
  onRun: () => void
}) {
  const { draft } = state
  const busy = state.phase === 'running' || state.phase === 'waiting'
  const [practice, setPractice] = useState(savedPractice)
  const toggle = (on: boolean) => {
    setPractice(on)
    savePractice(on)
    if (!on && state.phase === 'practicing') dispatch({ type: 'open', draft }) // back to the same form
  }
  return (
    <aside
      id="builder-panel"
      aria-label="Builder"
      style={{
        position: 'fixed',
        left: 12,
        bottom: 12,
        width: 440,
        maxWidth: 'calc(100vw - 24px)',
        maxHeight: 'calc(100vh - 200px)',
        overflow: 'auto',
        padding: '10px 14px',
        borderRadius: 8,
        background: theme.background,
        color: theme.label,
        boxShadow: '0 1px 4px rgba(0,0,0,.25)',
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <b style={{ flex: 1 }}>{OP_TITLE[draft.op.name] ?? draft.op.name}</b>
        <label style={{ fontSize: 12 }} title="Builder dựng lệnh nhưng không chạy; bạn tự chạy lệnh trong terminal">
          <input id="practice-toggle" type="checkbox" checked={practice} disabled={busy} onChange={(e) => toggle(e.target.checked)} /> Luyện tập
        </label>
        <button id="close-builder" onClick={() => dispatch({ type: 'cancel' })} disabled={busy} aria-label="Đóng">
          ×
        </button>
      </div>
      <BuildForm
        draft={draft}
        problems={state.preview?.problems ?? []}
        graph={graph}
        lab={lab}
        theme={theme}
        disabled={state.phase !== 'form' && state.phase !== 'failed'}
        onEdit={(field, value) => dispatch({ type: 'edit', field, value })}
      />
      <div style={{ marginTop: 10 }}>
        <CommandPanel
          state={state}
          canRun={lab.canRun}
          runBlocker={lab.runBlocker}
          practice={practice}
          events={events}
          theme={theme}
          onRun={onRun}
          onPractice={() => dispatch({ type: 'practice', since: events.at(-1)?.seq ?? 0, known: graph?.nodes.map((n) => n.id) ?? [] })}
          onRetry={() => dispatch({ type: 'open', draft })}
        />
      </div>
    </aside>
  )
}
