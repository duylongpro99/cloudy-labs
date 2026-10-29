// Property panel for the selected resource (PRD F3.4): an HTML overlay beside the canvas.
// A resource deleted while the panel is open stays on screen, marked as deleted, until it is closed.
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { resourceId, type SceneGraph } from '../graph/graph-to-scene'
import type { GraphEdge, GraphNode } from '../graph/types'
import type { Theme } from './theme'

// Props shown as warnings rather than as rows of the table.
const WARNING_PROPS = new Set(['privateIpOutOfCidr', 'note', 'hostPorts'])

const formatValue = (v: unknown) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))

function warnings(props: Record<string, unknown>): string[] {
  const out: string[] = []
  if (props.privateIpOutOfCidr) out.push('IP riêng nằm ngoài CIDR của subnet: Floci cấp IP từ mạng Docker.')
  if (typeof props.note === 'string') out.push(props.note)
  const ports = props.hostPorts as Record<string, number> | undefined
  if (ports && Object.keys(ports).length > 0) {
    out.push(`Không có IP công khai thật; truy cập từ máy qua ${Object.entries(ports).map(([p, h]) => `${p} → 127.0.0.1:${h}`).join(', ')}.`)
  }
  return out
}

export function PropertyPanel({ selected, scene, edges, theme, onClose }: { selected: string; scene: SceneGraph; edges: readonly GraphEdge[]; theme: Theme; onClose: () => void }) {
  const id = resourceId(selected)
  const current = scene.nodesById.get(id)
  // The last version seen, so a deleted resource can still be named.
  const last = useRef<GraphNode | null>(null)
  if (current) last.current = current
  else if (last.current?.id !== id) last.current = null
  const node = current ?? last.current
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => setCopied(false), [id])

  const label = (nid: string) => scene.nodesById.get(nid)?.label ?? nid
  const outgoing = edges.filter((e) => e.from === id)
  const incoming = edges.filter((e) => e.to === id)
  const props = node ? Object.entries(node.props).filter(([k]) => !WARNING_PROPS.has(k)) : []
  const notes = node ? warnings(node.props) : []
  const muted: CSSProperties = { opacity: 0.7 }

  return (
    <aside
      id="property-panel"
      data-id={id}
      data-deleted={current ? undefined : 'true'}
      style={{
        position: 'fixed',
        top: 12,
        right: 12,
        width: 340,
        maxHeight: 'calc(100vh - 24px)',
        overflow: 'auto',
        padding: '10px 14px',
        borderRadius: 8,
        background: theme.background,
        color: theme.label,
        boxShadow: '0 1px 4px rgba(0,0,0,.25)',
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ fontSize: 15, flex: 1, overflowWrap: 'anywhere' }}>{node?.label ?? id}</b>
        <button id="close-panel" onClick={onClose} aria-label="Đóng">
          ×
        </button>
      </div>
      {node && <div style={muted}>{node.kind}</div>}
      {!current && (
        <p id="panel-deleted" style={{ color: theme.edges.usesKey, fontWeight: 600 }}>
          Tài nguyên đã bị xoá
        </p>
      )}
      <div style={{ marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
        <code style={{ overflowWrap: 'anywhere' }}>{id}</code>
        <button
          id="copy-id"
          onClick={() => void navigator.clipboard?.writeText(id).then(() => setCopied(true), () => setCopied(false))}
        >
          {copied ? 'Đã chép' : 'Chép'}
        </button>
      </div>
      {notes.length > 0 && (
        <ul id="panel-warnings" style={{ margin: '8px 0 0', paddingLeft: 18 }}>
          {notes.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {props.length > 0 && (
        <table style={{ marginTop: 8, borderCollapse: 'collapse', width: '100%' }}>
          <tbody>
            {props.map(([k, v]) => (
              <tr key={k}>
                <td style={{ ...muted, padding: '2px 8px 2px 0', verticalAlign: 'top' }}>{k}</td>
                <td style={{ padding: '2px 0', overflowWrap: 'anywhere' }}>{formatValue(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(outgoing.length > 0 || incoming.length > 0) && (
        <ul id="panel-edges" style={{ margin: '8px 0 0', paddingLeft: 18 }}>
          {outgoing.map((e) => (
            <li key={e.id}>
              {e.kind} → {label(e.to)} {e.label && <span style={muted}>({e.label})</span>}
            </li>
          ))}
          {incoming.map((e) => (
            <li key={e.id}>
              {e.kind} ← {label(e.from)} {e.label && <span style={muted}>({e.label})</span>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
