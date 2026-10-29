// The builder's side panel: the open op's form above its command, output and status.
import type { ResourceGraph } from '../graph/types'
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
}

type Open = Exclude<BuilderState, { phase: 'idle' | 'dragging' | 'connecting' }>

export function BuilderPanel({ state, graph, lab, theme, dispatch, onRun }: {
  state: Open
  graph: ResourceGraph | null
  lab: LabInfo
  theme: Theme
  dispatch: (a: BuilderAction) => void
  onRun: () => void
}) {
  const { draft } = state
  const busy = state.phase === 'running' || state.phase === 'waiting'
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
        <CommandPanel state={state} canRun={lab.canRun} runBlocker={lab.runBlocker} theme={theme} onRun={onRun} onRetry={() => dispatch({ type: 'open', draft })} />
      </div>
    </aside>
  )
}
