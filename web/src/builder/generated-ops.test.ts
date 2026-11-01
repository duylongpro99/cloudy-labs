import { describe, expect, it } from 'vitest'
import type { GraphNode, ResourceGraph } from '../graph/types'
import type { OpSpec } from './builder-api'
import { fieldOptions } from './build-form'
import { connectOp } from './connect-rules'
import { createDraft, fixedDraft, opsOn, targetDraft } from './form-model'
import { jsonProblem } from './json-field'
import { expectMet } from './use-builder'
import { LAB, golden } from './test-fixtures'

// Ops shaped the way the server describes a registry op built from its botocore input shape.
const createDb: OpSpec = {
  name: 'create-db-instance', gesture: 'create', title: 'Tạo RDS', kind: 'rds-instance', generated: true,
  creates: 'rds-instance', containers: ['vpc'], container: { param: 'DBSubnetGroupName', by: 'label' }, nameField: 'DBInstanceIdentifier',
  defaults: { Engine: 'mysql', AllocatedStorage: '20' },
  fields: [
    { name: 'DBInstanceIdentifier', type: 'string', required: true, label: 'DBInstanceIdentifier', doc: 'The identifier.' },
    { name: 'Engine', type: 'enum', required: true, label: 'Engine', choices: ['mysql', 'postgres'] },
    { name: 'DBSubnetGroupName', type: 'string', required: false, label: 'Subnet group', ref: 'vpc', refBy: 'label' },
    { name: 'MultiAZ', type: 'boolean', required: false, label: 'MultiAZ' },
    { name: 'AllocatedStorage', type: 'integer', required: false, label: 'AllocatedStorage', advanced: true },
    { name: 'Port', type: 'integer', required: false, label: 'Port', advanced: true },
  ],
}
const putPolicy: OpSpec = {
  name: 'put-bucket-policy', gesture: 'attribute', title: 'Gắn bucket policy', generated: true, targets: ['vpc'], targetParam: 'Bucket',
  fields: [
    { name: 'Bucket', type: 'string', required: true, label: 'Bucket', ref: 'vpc', refBy: 'label' },
    { name: 'Policy', type: 'json', required: true, label: 'Policy', free: true },
  ],
}
const deleteUser: OpSpec = {
  name: 'delete-test-user', gesture: 'delete', title: 'Xoá user', generated: true, targets: ['test-user'], targetParam: 'UserName',
  fields: [{ name: 'UserName', type: 'string', required: true, label: 'UserName', ref: 'test-user', refBy: 'label' }],
}
const attachPolicy: OpSpec = {
  name: 'attach-role-policy', gesture: 'connect', title: 'Gắn policy', generated: true, source: 'test-policy', sourceParam: 'PolicyArn',
  targets: ['test-role'], targetParam: 'RoleName',
  fields: [
    { name: 'RoleName', type: 'string', required: true, label: 'RoleName', ref: 'test-role', refBy: 'label' },
    { name: 'PolicyArn', type: 'string', required: true, label: 'PolicyArn', ref: 'test-policy' },
  ],
}

const g = golden()
const vpc = g.nodes.find((n) => n.kind === 'vpc') as GraphNode
const withVpcName: ResourceGraph = { ...g, nodes: g.nodes.map((n) => (n.id === vpc.id ? { ...n, label: 'lab-vpc' } : n)) }

describe('generated ops', () => {
  it('open a create form with defaults, a suggested name and the tray locked', () => {
    const d = createDraft(createDb, { id: vpc.id, kind: 'vpc', label: 'lab-vpc' }, g, LAB)
    expect(d.params).toEqual({ DBInstanceIdentifier: 'lab-06-rds-instance-1', Engine: 'mysql', DBSubnetGroupName: 'lab-vpc', MultiAZ: '', AllocatedStorage: '20' })
    expect(d.locked).toEqual(['DBSubnetGroupName'])
  })

  it('lock what the gesture fixed but keep free fields editable', () => {
    const d = fixedDraft(putPolicy, { Bucket: 'lab-site', Policy: '{}' })
    expect(d.locked).toEqual(['Bucket'])
    expect(targetDraft(putPolicy, { id: 'x', label: 'lab-site' }).params).toEqual({ Bucket: 'lab-site', Policy: '' })
  })

  it('act on the nodes their targets name, by gesture', () => {
    const ops = [createDb, putPolicy, deleteUser]
    expect(opsOn(ops, 'vpc', ['attribute', 'modify']).map((o) => o.name)).toEqual(['put-bucket-policy'])
    expect(opsOn(ops, 'test-user', ['delete']).map((o) => o.name)).toEqual(['delete-test-user'])
    expect(opsOn(ops, 'vpc', ['delete'])).toEqual([])
  })

  it('connect two nodes through the source and target params', () => {
    const policy = { id: 'arn:aws:iam::000000000000:policy/p', kind: 'test-policy', label: 'p', props: {} }
    const role = { id: 'AROA1', kind: 'test-role', label: 'lab-role', props: {} }
    const r = connectOp([attachPolicy], policy, role)
    expect(r.ok && r.params).toEqual({ PolicyArn: policy.id, RoleName: 'lab-role' })
  })

  it('offer nodes, enums and booleans as options, empty when optional', () => {
    const [, engine, subnetGroup, multiAz] = createDb.fields ?? []
    expect(fieldOptions(engine, g, LAB)?.map((o) => o.value)).toEqual(['mysql', 'postgres'])
    expect(fieldOptions(multiAz, g, LAB)?.map((o) => o.value)).toEqual(['', 'true', 'false'])
    expect(fieldOptions(subnetGroup, withVpcName, LAB)).toContainEqual({ value: 'lab-vpc', text: `lab-vpc (${vpc.id})` })
    expect(fieldOptions(createDb.fields![0], g, LAB)).toBeNull()
  })

  it('say early when a JSON field is not JSON', () => {
    expect(jsonProblem('')).toBeNull()
    expect(jsonProblem('{"Version": "2012-10-17"}')).toBeNull()
    expect(jsonProblem('[{')).toMatch(/^Chưa phải JSON hợp lệ/)
  })

  it('count a delete once the node has left the graph', () => {
    expect(expectMet({ gone: vpc.id }, g)).toBe(false)
    expect(expectMet({ gone: 'vpc-deleted' }, g)).toBe(true)
  })
})
