// "Phân tích đường đi" (PRD F6.5): pick a source and a destination (a resource, "internet" or an
// IP/CIDR), a port and a protocol, and read hop by hop where the configuration lets the flow pass
// or stops it. The result is drawn in the scene by ReachabilityLayer; it is always labelled as an
// analysis of configuration, never as real traffic.
import { useState } from 'react'
import { BuilderError } from '../builder/builder-api'
import type { ResourceGraph } from '../graph/types'
import type { Theme } from '../scene/theme'
import { ANALYSIS_NOTE, analyseReachability, PROTOCOLS, REASON_TEXT, type Proto, type Reachability } from './reachability-api'

// What can be one end of a flow; mirrors ENDPOINT_KINDS in server reachability/analyze.py.
export const ENDPOINT_KINDS: ReadonlySet<string> = new Set(['instance', 'network-interface', 'lambda-function', 'db-instance', 'vpc-endpoint'])

export function endpointOptions(graph: ResourceGraph | null): { value: string; label: string }[] {
  const nodes = (graph?.nodes ?? []).filter((n) => ENDPOINT_KINDS.has(n.kind))
  return [{ value: 'internet', label: 'Internet' }, ...nodes.map((n) => ({ value: n.id, label: n.label === n.id ? n.id : `${n.label} (${n.id})` }))]
}

export function ReachabilityPanel({ graph, selected, theme, result, onResult, fetcher = fetch }: {
  graph: ResourceGraph | null
  selected: string | null // the object selected in the scene, offered as either end
  theme: Theme
  result: Reachability | null
  onResult: (r: Reachability | null) => void
  fetcher?: typeof fetch
}) {
  const [src, setSrc] = useState('internet')
  const [dst, setDst] = useState('')
  const [port, setPort] = useState('80')
  const [proto, setProto] = useState<Proto>('tcp')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const options = endpointOptions(graph)
  const label = (id: string) => graph?.nodes.find((n) => n.id === id)?.label ?? id
  const portNumber = Number(port)
  const valid = src.trim() !== '' && dst.trim() !== '' && Number.isInteger(portNumber) && portNumber >= 0 && portNumber <= 65535

  async function run() {
    setBusy(true)
    setError(null)
    try {
      onResult(await analyseReachability({ src: src.trim(), dst: dst.trim(), port: portNumber, proto }, fetcher))
    } catch (e) {
      onResult(null)
      setError(e instanceof BuilderError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <details id="reachability-panel" style={{ marginTop: 8 }} onToggle={(e) => !(e.currentTarget as HTMLDetailsElement).open && onResult(null)}>
      <summary style={{ cursor: 'pointer' }}>
        <b>Phân tích đường đi</b>
      </summary>
      <p className="reach-note" style={{ margin: '4px 0', fontSize: 12, opacity: 0.8 }}>{ANALYSIS_NOTE}</p>
      <datalist id="reach-endpoints">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </datalist>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 4, alignItems: 'center', fontSize: 13 }}>
        <label htmlFor="reach-src">Nguồn</label>
        <input id="reach-src" list="reach-endpoints" value={src} onChange={(e) => setSrc(e.target.value)} placeholder="id, internet hoặc IP" />
        <button className="reach-use-selected" data-end="src" disabled={!selected} onClick={() => selected && setSrc(selected)}>Đang chọn</button>
        <label htmlFor="reach-dst">Đích</label>
        <input id="reach-dst" list="reach-endpoints" value={dst} onChange={(e) => setDst(e.target.value)} placeholder="id, internet hoặc IP" />
        <button className="reach-use-selected" data-end="dst" disabled={!selected} onClick={() => selected && setDst(selected)}>Đang chọn</button>
        <label htmlFor="reach-port">Cổng</label>
        <span>
          <input id="reach-port" inputMode="numeric" value={port} onChange={(e) => setPort(e.target.value)} style={{ width: 70 }} />{' '}
          <select id="reach-proto" value={proto} onChange={(e) => setProto(e.target.value as Proto)}>
            {PROTOCOLS.map((p) => <option key={p} value={p}>{p === '-1' ? 'mọi giao thức' : p}</option>)}
          </select>
        </span>
        <button id="reach-run" disabled={!valid || busy} onClick={run}>{busy ? 'Đang phân tích…' : 'Phân tích'}</button>
      </div>
      {error && <p id="reach-error" role="status" style={{ margin: '6px 0 0', color: theme.failed }}>{error}</p>}
      {result && (
        <div id="reach-result" data-ok={result.ok} style={{ marginTop: 6 }}>
          <div style={{ color: result.ok ? theme.achieved : theme.failed, fontWeight: 600 }}>
            {result.ok
              ? 'Tới được đích (theo cấu hình)'
              : `Bị chặn tại ${label(result.blockedAt ?? '')}: ${REASON_TEXT[result.reason] ?? result.reason}`}
          </div>
          <ol className="reach-hops" style={{ margin: '4px 0 0', paddingLeft: 20, fontSize: 12 }}>
            {result.hops.map((h, i) => (
              <li key={i} className="reach-hop" data-verdict={h.verdict} style={{ color: h.verdict === 'deny' ? theme.failed : 'inherit' }}>
                {h.resource_id === 'internet' ? 'Internet' : label(h.resource_id)} · {REASON_TEXT[h.reason] ?? h.reason}
                {h.rule && <span style={{ opacity: 0.75 }}> · {h.rule}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </details>
  )
}
