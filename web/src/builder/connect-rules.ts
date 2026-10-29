// Which edge a learner may draw between two objects, and the op it becomes (PRD F4.6).
// The pairs come from the server's connect ops (`source`, `targets`); the extra conditions
// here only explain early what the server's validation would refuse anyway.
import type { GraphNode } from '../graph/types'
import type { OpSpec, Params } from './builder-api'
import { kindLabel } from './drop-targets'

export const DEFAULT_DESTINATION = '0.0.0.0/0'

export const connectOpsFrom = (ops: readonly OpSpec[], kind: string) => ops.filter((o) => o.gesture === 'connect' && o.source === kind)

export type ConnectCheck = { ok: true; op: OpSpec; params: Params } | { ok: false; reason: string }

export function connectOp(ops: readonly OpSpec[], source: GraphNode, target: GraphNode): ConnectCheck {
  const candidates = connectOpsFrom(ops, source.kind)
  if (candidates.length === 0) return { ok: false, reason: `${kindLabel(source.kind)} không có cạnh nào để nối` }
  const op = candidates.find((o) => (o.targets ?? []).includes(target.kind))
  if (!op) {
    const allowed = [...new Set(candidates.flatMap((o) => o.targets ?? []))].map(kindLabel).join(', ')
    return { ok: false, reason: `${kindLabel(source.kind)} không nối được tới ${kindLabel(target.kind)}; chỉ nối tới ${allowed}` }
  }
  switch (op.name) {
    case 'attach-internet-gateway':
      if (source.props.attachedVpc) return { ok: false, reason: `${source.label} đã gắn vào ${String(source.props.attachedVpc)}` }
      return { ok: true, op, params: { igwId: source.id, vpcId: target.id } }
    case 'create-route':
      if (target.kind === 'nat' && target.props.state !== 'available') {
        return { ok: false, reason: `${target.label} đang ${String(target.props.state ?? 'chưa sẵn sàng')}; chờ tới available rồi mới route tới nó` }
      }
      return { ok: true, op, params: { routeTableId: source.id, targetId: target.id, destination: DEFAULT_DESTINATION } }
    case 'associate-route-table':
      return { ok: true, op, params: { routeTableId: source.id, subnetId: target.id } }
  }
  return { ok: false, reason: `${op.name}: chưa hỗ trợ trong builder` }
}
