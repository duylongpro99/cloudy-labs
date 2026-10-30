// The form of one builder op (PRD F4.3): the fields the op takes, those fixed by the gesture shown
// read-only, and each problem from the server's validation next to the field it is about.
import type { CSSProperties } from 'react'
import type { ResourceGraph } from '../graph/types'
import type { Theme } from '../scene/theme'
import type { LabInfo, Problem } from './builder-api'
import { freeElasticIps, groupsIn, vpcOf, type Draft } from './form-model'

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
  description: 'Mô tả',
  groupId: 'Security Group',
  protocol: 'Giao thức',
  port: 'Cổng (một số, ví dụ 80)',
  imageId: 'AMI',
  instanceType: 'Instance type',
  securityGroupId: 'Security Group',
  keyName: 'Key Pair',
  userData: 'UserData',
  instanceId: 'EC2 Instance',
}

const PLACEHOLDER: Record<string, string> = { cidr: '10.0.1.0/24', destination: '0.0.0.0/0', port: '80' }

// "-1" is every protocol and every port.
const PROTOCOLS = ['tcp', 'udp', 'icmp', '-1']
const MULTILINE = new Set(['userData'])

// A web server listening on 0.0.0.0:80 cannot start on Floci: IMDS holds that address in the instance.
const BINDS_ALL = /0\.0\.0\.0:80|--bind 0\.0\.0\.0|http\.server 80(?!.*--bind)/

export function userDataHint(script: string): string | null {
  const code = script.split('\n').filter((line) => !line.trimStart().startsWith('#')).join('\n') // comments may name 0.0.0.0:80
  return BINDS_ALL.test(code) ? 'Trên Floci, IMDS đã chiếm 0.0.0.0:80 trong instance; bind từng địa chỉ IPv4 của instance trừ lo (xem docs/emulator-differences.md)' : null
}

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
    if (field === 'imageId') return lab.images
    if (field === 'instanceType') return lab.instanceTypes
    if (field === 'protocol') return PROTOCOLS
    if (field === 'securityGroupId') {
      const vpc = graph && vpcOf(graph, draft.params.subnetId ?? '')
      return graph && vpc ? groupsIn(graph, vpc).map((n) => n.id) : []
    }
    if (field === 'keyName') return ['', ...(graph?.nodes.filter((n) => n.kind === 'key-pair').map((n) => n.label) ?? [])]
    return null
  }
  const optionText = (field: string, o: string) => {
    if (field === 'keyName' && o === '') return '(không dùng key pair)'
    if (field === 'protocol' && o === '-1') return '-1 (mọi giao thức)'
    return field === 'allocationId' || field === 'securityGroupId' ? label(o) : o
  }
  const hint = 'userData' in draft.params ? userDataHint(draft.params.userData) : null

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
                    {optionText(field, o)}
                  </option>
                ))}
              </select>
            ) : MULTILINE.has(field) ? (
              <textarea
                id={id}
                value={value}
                disabled={disabled}
                spellCheck={false}
                rows={field === 'userData' ? 8 : 2}
                onChange={(e) => onEdit(field, e.target.value)}
                style={field === 'userData' ? { ...input, fontFamily: 'ui-monospace, monospace', fontSize: 12 } : input}
                aria-invalid={own.length > 0}
                aria-describedby={own.length > 0 ? `problem-${field}` : undefined}
              />
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
            {field === 'userData' && hint && (
              <div id="user-data-hint" style={{ fontSize: 12, marginTop: 2, opacity: 0.85 }}>
                {hint}
              </div>
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
