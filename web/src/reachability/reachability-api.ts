// Static reachability (PRD F6.5): the lab-server reads the network configuration and says whether
// traffic from src could reach dst on a port, hop by hop. Nothing is sent; it is an analysis.
// Mirrors Reachability.to_dict in server/src/cloudy_labs/reachability/model.py.
import { request, STATUS_TEXT } from '../builder/builder-api'

export type Proto = 'tcp' | 'udp' | 'icmp' | '-1'
export const PROTOCOLS: readonly Proto[] = ['tcp', 'udp', 'icmp', '-1']

export interface ReachQuery {
  src: string // a resource id or name, "internet", or an IPv4 address or CIDR
  dst: string
  port: number
  proto: Proto
}

export interface ReachHop {
  resource_id: string // "internet" for the outside world
  kind: string
  verdict: 'allow' | 'deny' | 'forward'
  reason: string
  rule: string | null
}

export interface Reachability {
  ok: boolean
  blockedAt: string | null
  reason: string
  label: 'analysed'
  hops: ReachHop[]
}

export const ANALYSIS_NOTE = 'Phân tích cấu hình, không phải traffic thật'

// Why a hop passed or stopped the flow, for the learner. Codes from model.py REASONS.
export const REASON_TEXT: Record<string, string> = {
  allowed: 'cho phép',
  routed: 'chuyển tiếp',
  delivered: 'tới đích',
  'no-matching-rule': 'không có rule nào cho phép',
  'denied-by-rule': 'bị một rule chặn',
  'return-denied': 'chiều về bị chặn (NACL stateless, cổng ephemeral)',
  'no-route': 'không có route tới đích',
  blackhole: 'route blackhole',
  'route-target-unknown': 'route trỏ tới đích không rõ',
  'no-public-ip': 'không có IP public',
  'not-transitive': 'peering không bắc cầu',
  'no-return-route': 'không có route chiều về',
  'loop-detected': 'route tạo vòng lặp',
  'endpoint-not-associated': 'route table không gắn với endpoint',
  'unsupported-target': 'loại target chưa được phân tích',
}

const TEXT = { ...STATUS_TEXT, 422: 'Truy vấn không hợp lệ', 503: 'Chưa phân tích được' }

export function analyseReachability(q: ReachQuery, fetcher: typeof fetch = fetch): Promise<Reachability> {
  return request<Reachability>(
    '/api/reachability',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) },
    fetcher,
    TEXT,
  )
}
