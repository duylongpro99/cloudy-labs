// Synthetic, seeded resource tree for the benchmark: exactly 200 nodes and 60 edges.
// This is a performance fixture, not learner-facing data.

export type GroupKind = 'region' | 'vpc' | 'az' | 'subnet-public' | 'subnet-private'
export type LeafKind = 'instance' | 'nat' | 'igw'

export interface FixtureNode {
  id: string
  label: string
  kind: GroupKind | LeafKind
  parent: string | null
}

export interface FixtureEdge {
  from: string
  to: string
}

export interface Fixture {
  nodes: FixtureNode[]
  edges: FixtureEdge[]
}

export const TOTAL_NODES = 200
export const TOTAL_EDGES = 60

// mulberry32: tiny deterministic PRNG so every run builds the identical scene.
function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function buildFixture(seed = 42): Fixture {
  const rand = rng(seed)
  const nodes: FixtureNode[] = []
  const edges: FixtureEdge[] = []
  const add = (n: FixtureNode) => (nodes.push(n), n.id)

  const region = add({ id: 'region', label: 'Vùng us-east-1', kind: 'region', parent: null })
  const subnets: { id: string; vpc: string; public: boolean; az: number }[] = []
  const igws: string[] = []

  for (let v = 0; v < 2; v++) {
    const vpc = add({ id: `vpc-${v}`, label: `VPC ${v === 0 ? 'sản xuất' : 'thử nghiệm'}`, kind: 'vpc', parent: region })
    igws.push(add({ id: `igw-${v}`, label: `Cổng Internet ${v + 1}`, kind: 'igw', parent: vpc }))
    for (let z = 0; z < 3; z++) {
      const az = add({ id: `az-${v}-${z}`, label: `us-east-1${'abc'[z]}`, kind: 'az', parent: vpc })
      for (const isPublic of [true, false]) {
        const id = add({
          id: `subnet-${v}-${z}-${isPublic ? 'pub' : 'pri'}`,
          label: `Mạng con ${isPublic ? 'công khai' : 'riêng tư'} ${z + 1}`,
          kind: isPublic ? 'subnet-public' : 'subnet-private',
          parent: az,
        })
        subnets.push({ id, vpc, public: isPublic, az: z })
      }
    }
  }

  // One NAT per public subnet, routed to its VPC's IGW.
  const natBySubnet = new Map<string, string>()
  for (const s of subnets.filter((s) => s.public)) {
    const nat = add({ id: `nat-${s.id}`, label: 'Cổng NAT', kind: 'nat', parent: s.id })
    natBySubnet.set(`${s.vpc}-${s.az}`, nat)
    edges.push({ from: nat, to: igws[Number(s.vpc.slice(-1))] })
  }

  // Fill the rest with instances spread over subnets, weighted toward private subnets.
  const privateInstances: { id: string; key: string }[] = []
  let i = 0
  while (nodes.length < TOTAL_NODES) {
    const s = subnets[Math.floor(rand() * subnets.length)]
    if (s.public && rand() < 0.4) continue
    const id = add({ id: `i-${String(i).padStart(3, '0')}`, label: `Máy chủ ${i + 1}`, kind: 'instance', parent: s.id })
    if (!s.public) privateInstances.push({ id, key: `${s.vpc}-${s.az}` })
    i++
  }

  // Remaining edges: private instances to the NAT of their AZ (the 0.0.0.0/0 route).
  for (const p of privateInstances) {
    if (edges.length >= TOTAL_EDGES) break
    edges.push({ from: p.id, to: natBySubnet.get(p.key)! })
  }

  if (nodes.length !== TOTAL_NODES || edges.length !== TOTAL_EDGES) {
    throw new Error(`fixture has ${nodes.length} nodes / ${edges.length} edges`)
  }
  return { nodes, edges }
}
