import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { actionKinds, edgeStyleOf, kindLabel, kindView, parseRegistry, registryData, setRegistry } from './registry'
import bundled from './registry.json'

const iconDir = resolve(import.meta.dirname, '../scene/aws-objects/icons')

describe('bundled registry', () => {
  afterEach(() => setRegistry(parseRegistry(bundled)))

  it('gives every kind except outline-only an icon file present in icons/', () => {
    for (const k of registryData().kinds) {
      if (k.role === 'outline-only') continue
      expect(k.icon, k.kind).toBeTruthy()
      expect(existsSync(resolve(iconDir, k.icon!)), `${k.kind}: ${k.icon}`).toBe(true)
      expect(kindView(k.kind).fallback, k.kind).toBeFalsy()
    }
  })

  it('names copied files after their source in the AWS package', () => {
    for (const k of registryData().kinds.filter((k) => k.source)) expect(k.source!.endsWith(`/${k.icon}`), k.kind).toBe(true)
  })

  it('lists every icon file and the fallback in NOTICE.md', () => {
    const notice = readFileSync(resolve(iconDir, 'NOTICE.md'), 'utf8')
    for (const k of registryData().kinds.filter((k) => k.icon)) expect(notice, k.kind).toContain(k.icon!)
    expect(notice).toContain('generic-resource.svg')
  })

  it('draws an unknown kind as a labelled general fallback', () => {
    const v = kindView('mystery-thing')
    expect(v).toMatchObject({ kind: 'mystery-thing', label: 'mystery-thing', role: 'block', category: 'general', icon: 'generic-resource.svg', fallback: true })
    expect(kindView('mystery-thing')).toBe(v)
  })

  it('keeps a known kind label and category when its icon is not bundled', () => {
    const data = parseRegistry(bundled)
    setRegistry({ ...data, kinds: [...data.kinds, { ...data.kinds.find((k) => k.kind === 'instance')!, kind: 'test-only', label: 'Test only', icon: 'not-bundled.svg' }] })
    expect(kindView('test-only')).toMatchObject({ label: 'Test only', category: 'compute', icon: 'generic-resource.svg', fallback: true })
  })

  it('maps edge kinds to styles and an unknown one to reference', () => {
    expect(edgeStyleOf('route')).toBe('route')
    expect(edgeStyleOf('attached')).toBe('attach')
    expect(edgeStyleOf('weird-link')).toBe('reference')
  })

  it('finds the kinds an action names, longest noun first', () => {
    expect(actionKinds('CreateVpc')).toEqual(['vpc'])
    expect(actionKinds('CreateRouteTable', 'ec2')).toEqual(['route-table'])
    expect(actionKinds('CreateSubnet').sort()).toEqual(['subnet-private', 'subnet-public'])
    expect(actionKinds('RunInstances')).toEqual(['instance'])
    expect(actionKinds('DoSomethingElse')).toEqual([])
  })

  it('reads an action within the service api-tap reported, by its signing name', () => {
    expect(actionKinds('CreateRoute', 'ec2')).toEqual(['route-table'])
    expect(actionKinds('CreateRoute', 'apigateway')).toEqual(['apigateway-http-api'])
    expect(actionKinds('CreateCluster', 'ecs')).toEqual(['ecs-cluster'])
    expect(actionKinds('CreateCluster', 'eks')).toEqual(['eks-cluster'])
    expect(actionKinds('PutMetricAlarm', 'monitoring')).toEqual(['cloudwatch-alarm'])
    expect(actionKinds('CreateAccessKey', 'iam')).not.toContain('kms-key')
    expect(actionKinds('CreateRoute', 'nothing-here')).toEqual([])
  })

  it('labels the builder subnet alias and falls back to the kind name', () => {
    expect(kindLabel('subnet')).toBe('Subnet')
    expect(kindLabel('mystery-thing')).toBe('mystery-thing')
  })

  it('refuses a registry without kinds', () => {
    expect(() => parseRegistry({})).toThrow()
  })
})
