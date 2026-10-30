// The form a builder op opens with: suggested values and which fields the gesture already fixed.
import type { GraphNode, ResourceGraph } from '../graph/types'
import type { LabInfo, OpSpec, Params } from './builder-api'

export interface Draft {
  op: OpSpec
  params: Params
  locked: string[] // fields decided by where the learner dropped or what they connected
  rev: number // bumped on every edit, so a late preview of an older form is ignored
}

export const SUBNET_KINDS = new Set(['subnet-public', 'subnet-private'])

export function parentOf(graph: ResourceGraph, id: string): string | null {
  return graph.contains.find((c) => c.child === id)?.parent ?? null
}

export function vpcOf(graph: ResourceGraph, id: string): string | null {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  for (let cur: string | null = id; cur; cur = parentOf(graph, cur)) if (byId.get(cur)?.kind === 'vpc') return cur
  return null
}

const subnetsIn = (graph: ResourceGraph, vpc: string) => graph.nodes.filter((n) => SUBNET_KINDS.has(n.kind) && vpcOf(graph, n.id) === vpc)

function parseCidr(cidr: string): { base: number; prefix: number } | null {
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)\/(\d+)$/.exec(cidr)
  if (!m) return null
  const base = m.slice(1, 5).reduce((acc, o) => acc * 256 + Number(o), 0)
  return { base, prefix: Number(m[5]) }
}

const formatIp = (n: number) => [24, 16, 8, 0].map((s) => Math.floor(n / 2 ** s) % 256).join('.')

// The first /24 inside the VPC's block that no subnet of it overlaps; "" when none is free.
export function nextFreeSubnet(vpcCidr: string, taken: readonly string[]): string {
  const vpc = parseCidr(vpcCidr)
  if (!vpc || vpc.prefix > 24) return ''
  const used = taken.map(parseCidr).filter((c) => c !== null).map((c) => [c.base, c.base + 2 ** (32 - c.prefix)] as const)
  const size = 256
  for (let start = vpc.base; start < vpc.base + 2 ** (32 - vpc.prefix); start += size) {
    if (used.every(([a, b]) => start + size <= a || start >= b)) return `${formatIp(start)}/24`
  }
  return ''
}

export const freeElasticIps = (graph: ResourceGraph): GraphNode[] =>
  graph.nodes.filter((n) => n.kind === 'elastic-ip' && !graph.edges.some((e) => e.kind === 'attached' && e.from === n.id))

// A Name tag that is not taken yet, e.g. "lab06-vpc-2".
export function suggestName(graph: ResourceGraph, lab: LabInfo, kind: string): string {
  const prefix = `${lab.id.replace(/^fixture-/, '').replace(/[^A-Za-z0-9.-]/g, '')}-${kind}`
  const names = new Set(graph.nodes.map((n) => n.label))
  for (let i = 1; ; i++) if (!names.has(`${prefix}-${i}`)) return `${prefix}-${i}`
}

// The form after dropping a create op on a tray.
export function createDraft(op: OpSpec, tray: { id: string; kind: string; label: string }, graph: ResourceGraph, lab: LabInfo): Draft {
  const params: Params = { name: suggestName(graph, lab, op.creates ?? 'resource') }
  const locked: string[] = []
  const vpc = vpcOf(graph, tray.id)
  switch (op.name) {
    case 'create-vpc': {
      const used = new Set(graph.nodes.filter((n) => n.kind === 'vpc').map((n) => n.props.cidr))
      params.cidr = lab.cidrs.find((c) => !used.has(c)) ?? ''
      break
    }
    case 'create-subnet': {
      const vpcNode = graph.nodes.find((n) => n.id === vpc)
      const subnets = vpc ? subnetsIn(graph, vpc) : []
      params.vpcId = vpc ?? ''
      params.cidr = nextFreeSubnet(String(vpcNode?.props.cidr ?? ''), subnets.map((s) => String(s.props.cidr ?? '')))
      if (tray.kind === 'az') {
        params.az = tray.label
        locked.push('az')
      } else {
        const used = new Set(subnets.map((s) => s.props.az))
        params.az = lab.azs.find((az) => !used.has(az)) ?? lab.azs[0] ?? ''
      }
      locked.push('vpcId')
      break
    }
    case 'create-nat-gateway':
      params.subnetId = tray.id
      params.allocationId = freeElasticIps(graph)[0]?.id ?? ''
      locked.push('subnetId')
      break
    case 'create-route-table':
      params.vpcId = vpc ?? ''
      locked.push('vpcId')
      break
    case 'create-security-group':
      params.vpcId = vpc ?? ''
      params.description = 'Lab web server'
      locked.push('vpcId')
      break
    case 'run-instances':
      params.subnetId = tray.id
      params.imageId = lab.images[0] ?? ''
      params.instanceType = lab.instanceTypes[0] ?? ''
      params.securityGroupId = (vpc ? groupsIn(graph, vpc) : [])[0]?.id ?? ''
      params.keyName = graph.nodes.find((n) => n.kind === 'key-pair')?.label ?? ''
      params.userData = lab.userData
      locked.push('subnetId')
      break
  }
  return { op, params, locked, rev: 0 }
}

// The security groups of a VPC, the learner's own before the default one.
export const groupsIn = (graph: ResourceGraph, vpc: string): GraphNode[] =>
  graph.nodes
    .filter((n) => n.kind === 'security-group' && vpcOf(graph, n.id) === vpc)
    .sort((a, b) => Number(a.props.groupName === 'default') - Number(b.props.groupName === 'default'))

// Fields of a connect or attribute op the learner still fills in; every other id comes from the gesture.
const FREE_FIELDS = new Set(['destination', 'protocol', 'port', 'cidr'])

export function fixedDraft(op: OpSpec, params: Params): Draft {
  return { op, params, locked: Object.keys(params).filter((k) => !FREE_FIELDS.has(k)), rev: 0 }
}

// A new inbound rule for a security group, suggesting the web server's rule.
export const ingressDraft = (op: OpSpec, groupId: string): Draft => fixedDraft(op, { groupId, protocol: 'tcp', port: '80', cidr: '0.0.0.0/0' })
