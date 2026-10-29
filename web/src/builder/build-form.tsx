// The form of one builder op (PRD F4.3): the fields the op takes, those fixed by the gesture shown
// read-only, and each problem from the server's validation next to the field it is about.
import type { CSSProperties } from 'react'
import type { ResourceGraph } from '../graph/types'
import type { Theme } from '../scene/theme'
import type { LabInfo, Problem } from './builder-api'
import { freeElasticIps, type Draft } from './form-model'

const FIELD_LABEL: Record<string, string> = {
  name: 'Name (tag)',
  cidr: 'CIDR',
  vpcId: 'VPC',
  az: 'Availability Zone',
  subnetId: 'Subnet',
  allocationId: 'Elastic IP',
  igwId: 'Internet Gateway',
  routeTableId: 'Route Table',
  targetId: 'Đích (IGW hoặc NAT)',
  destination: 'Dải đích (CIDR)',
}

const PLACEHOLDER: Record<string, string> = { cidr: '10.0.1.0/24', destination: '0.0.0.0/0' }

export function BuildForm({ draft, problems, graph, lab, theme, disabled, onEdit }: {
  draft: Draft
  problems: readonly Problem[]
  graph: ResourceGraph | null
  lab: LabInfo
  theme: Theme
  disabled: boolean
  onEdit: (field: string, value: string) => void
}) {
  const fields = Object.keys(draft.params)
  const general = problems.filter((p) => !fields.includes(p.field))
  const label = (id: string) => {
    const n = graph?.nodes.find((x) => x.id === id)
    return n && n.label !== id ? `${n.label} (${id})` : id
  }
  const input: CSSProperties = { width: '100%', boxSizing: 'border-box', font: 'inherit' }
  const choices = (field: string): string[] | null => {
    if (field === 'az' && lab.azs.length > 0) return lab.azs
    if (field === 'allocationId') return graph ? freeElasticIps(graph).map((n) => n.id) : []
    return null
  }

  return (
    <form id="build-form" data-op={draft.op.name} onSubmit={(e) => e.preventDefault()} style={{ display: 'grid', gap: 8 }}>
      {general.map((p) => (
        <p key={p.message} className="problem" data-field={p.field} style={{ margin: 0, color: theme.edges.usesKey }}>
          {p.message}
        </p>
      ))}
      {fields.map((field) => {
        const id = `field-${field}`
        const value = draft.params[field]
        const own = problems.filter((p) => p.field === field)
        const options = choices(field)
        return (
          <div key={field}>
            <label htmlFor={id} style={{ display: 'block', opacity: 0.75, fontSize: 12 }}>
              {FIELD_LABEL[field] ?? field}
            </label>
            {draft.locked.includes(field) ? (
              <output id={id} style={{ display: 'block', overflowWrap: 'anywhere' }}>
                {label(value)}
              </output>
            ) : options ? (
              <select id={id} value={value} disabled={disabled} onChange={(e) => onEdit(field, e.target.value)} style={input} aria-invalid={own.length > 0}>
                {!options.includes(value) && <option value={value}>{value === '' ? '(chưa có)' : value}</option>}
                {options.map((o) => (
                  <option key={o} value={o}>
                    {field === 'allocationId' ? label(o) : o}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={id}
                value={value}
                disabled={disabled}
                placeholder={PLACEHOLDER[field]}
                spellCheck={false}
                autoComplete="off"
                onChange={(e) => onEdit(field, e.target.value)}
                style={input}
                aria-invalid={own.length > 0}
                aria-describedby={own.length > 0 ? `problem-${field}` : undefined}
              />
            )}
            {own.length > 0 && (
              <div id={`problem-${field}`} className="problem" data-field={field} style={{ color: theme.edges.usesKey, fontSize: 12, marginTop: 2 }}>
                {own.map((p) => (
                  <div key={p.message}>{p.message}</div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </form>
  )
}
