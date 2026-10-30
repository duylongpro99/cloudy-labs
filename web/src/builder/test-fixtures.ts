// Shared data for the builder's unit tests: the server's op catalogue for the fixture lab and
// the server's golden graph, read from disk so the tests follow the server's contract.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parseGraph, type GraphNode, type ResourceGraph } from '../graph/types'
import type { LabInfo, OpSpec } from './builder-api'

// Mirrors builder/ops.py `catalog` for a lab whose palette lists every kind.
export const OPS: OpSpec[] = [
  { name: 'create-vpc', gesture: 'create', creates: 'vpc', containers: ['region'] },
  { name: 'create-subnet', gesture: 'create', creates: 'subnet', containers: ['vpc', 'az'] },
  { name: 'create-internet-gateway', gesture: 'create', creates: 'igw', containers: ['region'] },
  { name: 'attach-internet-gateway', gesture: 'connect', source: 'igw', targets: ['vpc'] },
  { name: 'allocate-address', gesture: 'create', creates: 'elastic-ip', containers: ['region'] },
  { name: 'create-nat-gateway', gesture: 'create', creates: 'nat', containers: ['subnet-public'] },
  { name: 'create-route-table', gesture: 'create', creates: 'route-table', containers: ['vpc'] },
  { name: 'create-route', gesture: 'connect', source: 'route-table', targets: ['igw', 'nat'] },
  { name: 'associate-route-table', gesture: 'connect', source: 'route-table', targets: ['subnet-public', 'subnet-private'] },
  { name: 'modify-vpc-attribute', gesture: 'attribute', targets: ['vpc'] },
  { name: 'modify-subnet-attribute', gesture: 'attribute', targets: ['subnet-public', 'subnet-private'] },
  { name: 'create-security-group', gesture: 'create', creates: 'security-group', containers: ['vpc'] },
  { name: 'authorize-security-group-ingress', gesture: 'attribute', targets: ['security-group'] },
  { name: 'create-key-pair', gesture: 'create', creates: 'key-pair', containers: ['region'] },
  { name: 'run-instances', gesture: 'create', creates: 'instance', containers: ['subnet-public', 'subnet-private'] },
  { name: 'modify-instance-attribute', gesture: 'connect', source: 'security-group', targets: ['instance'] },
]

export const op = (name: string) => OPS.find((o) => o.name === name)!

export const LAB: LabInfo = {
  id: 'fixture-lab-06',
  title: 'Fixture lab 6',
  attempt: 7,
  tasks: [],
  palette: ['vpc', 'subnet', 'igw', 'elastic-ip', 'nat', 'route-table'],
  tags: { lab: 'fixture-lab-06' },
  cidrs: ['10.66.0.0/16'],
  ops: OPS,
  azs: ['us-east-1a', 'us-east-1b', 'us-east-1c'],
  images: ['ami-amazonlinux2023-arm64'],
  instanceTypes: ['t4g.micro', 't4g.small'],
  userData: '#!/bin/bash\npython3 -m http.server 80 --bind 10.67.1.10\n',
  canRun: true,
  runBlocker: null,
}

export const LAB07: LabInfo = { ...LAB, id: 'fixture-lab-07', title: 'Fixture lab 7', palette: ['security-group', 'key-pair', 'instance'], tags: { lab: 'fixture-lab-07' }, cidrs: ['10.67.0.0/16'] }

const GOLDEN = resolve(import.meta.dirname, '../../../server/tests/fixtures/graph/lab-06-07.graph.json')
export const golden = (): ResourceGraph => parseGraph(JSON.parse(readFileSync(GOLDEN, 'utf8')))
export const node = (g: ResourceGraph, id: string): GraphNode => g.nodes.find((n) => n.id === id)!
