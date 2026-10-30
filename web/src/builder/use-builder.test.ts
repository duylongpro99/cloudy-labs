import { describe, expect, it } from 'vitest'
import { BuilderError, type Preview, type RunOutcome } from './builder-api'
import { fixedDraft } from './form-model'
import { IDLE, WAIT_MS, expectMet, practiceMet, previewCurrent, reduce, type BuilderAction, type BuilderState } from './use-builder'
import { golden, op } from './test-fixtures'

const g = golden()
const draft = fixedDraft(op('create-route'), { routeTableId: 'rtb-1', targetId: 'igw-1', destination: '0.0.0.0/0' })
const preview: Preview = { command: 'aws ec2 create-route ...', argv: ['aws'], problems: [], practiceExpect: { edge: 'route:rtb-1->igw-1:0.0.0.0/0' } }
const outcome = (o: Partial<RunOutcome> = {}): RunOutcome => ({
  command: preview.command, exitCode: 0, stdout: '{}', stderr: '', durationMs: 120,
  expect: { edge: 'route:rtb-1->igw-1:0.0.0.0/0' }, ...o,
})
const run = (...actions: BuilderAction[]) => actions.reduce<BuilderState>(reduce, IDLE)
const ready = (): BuilderAction[] => [{ type: 'open', draft }, { type: 'previewed', rev: 0, preview, error: null }]
const withEdge = { ...g, edges: [...g.edges, { id: 'route:rtb-1->igw-1:0.0.0.0/0', kind: 'route' as const, from: 'rtb-1', to: 'igw-1', label: '0.0.0.0/0' }] }

describe('expectMet', () => {
  it('reads nodes, node props and edges from the graph', () => {
    expect(expectMet({ node: 'vpc-149d0439' }, g)).toBe(true)
    expect(expectMet({ node: 'vpc-nope' }, g)).toBe(false)
    expect(expectMet({ node: 'igw-34ddd4cd', prop: 'attachedVpc', value: 'vpc-149d0439' }, g)).toBe(true)
    expect(expectMet({ node: 'subnet-44acdeb7', prop: 'mapPublicIpOnLaunch', value: true }, g)).toBe(false)
    expect(expectMet({ edge: 'route:rtb-509e5b33->igw-34ddd4cd:0.0.0.0/0' }, g)).toBe(true)
    // When the server could not read an id it only asks for a newer graph than the one before the run.
    expect(expectMet({ after: g.version }, g)).toBe(false)
    expect(expectMet({ after: g.version }, { ...g, version: g.version + 1 })).toBe(true)
  })

  it('finds a security group rule among the group\'s rules', () => {
    const sg = 'sg-dbd2e6007fa2e7eef'
    expect(expectMet({ node: sg, prop: 'ingress', includes: { protocol: 'tcp', from: 80, to: 80, source: '0.0.0.0/0' } }, g)).toBe(true)
    expect(expectMet({ node: sg, prop: 'ingress', includes: { protocol: 'tcp', from: 22, to: 22, source: '0.0.0.0/0' } }, g)).toBe(false)
    expect(expectMet({ node: sg, prop: 'ingress', includes: { protocol: 'tcp', from: 443, to: 443, source: '0.0.0.0/0' } }, g)).toBe(false)
    expect(expectMet({ node: 'sg-b58b05ddff613fe13', prop: 'ingress', includes: { protocol: '-1', source: '10.0.0.0/8' } }, g)).toBe(false)
  })
})

describe('practiceMet', () => {
  it('waits for a resource of that kind with the name the learner typed', () => {
    expect(practiceMet({ kind: 'vpc', label: 'lab06-vpc' }, g)).toBe(true)
    expect(practiceMet({ kind: 'security-group', label: 'lab07-web' }, g)).toBe(true)
    const subnet = g.nodes.find((n) => n.kind === 'subnet-public')!
    expect(practiceMet({ kind: 'subnet', label: subnet.label }, g)).toBe(true)
    expect(practiceMet({ kind: 'vpc', label: subnet.label }, g)).toBe(false)
    expect(practiceMet({ kind: 'security-group', label: 'not-typed-yet' }, g)).toBe(false)
  })

  it('does not count a resource of that name that existed when the command was copied', () => {
    const vpc = g.nodes.find((n) => n.kind === 'vpc' && n.label === 'lab06-vpc')!
    expect(practiceMet({ kind: 'vpc', label: 'lab06-vpc' }, g, [vpc.id])).toBe(false)
    const again = { ...g, nodes: [...g.nodes, { ...vpc, id: 'vpc-new' }] }
    expect(practiceMet({ kind: 'vpc', label: 'lab06-vpc' }, again, [vpc.id])).toBe(true)
  })

  it('reads edges and props like a run does', () => {
    expect(practiceMet({ edge: 'route:rtb-1->igw-1:0.0.0.0/0' }, g)).toBe(false)
    expect(practiceMet({ edge: 'route:rtb-1->igw-1:0.0.0.0/0' }, withEdge)).toBe(true)
  })
})

describe('builder state', () => {
  it('drags, hovers, and opens the form on a valid drop', () => {
    let s = run({ type: 'drag', kind: 'vpc', op: op('create-vpc') }, { type: 'hover', hover: 'us-east-1', reason: null })
    expect(s).toMatchObject({ phase: 'dragging', hover: 'us-east-1' })
    s = reduce(s, { type: 'drop', draft, reason: null })
    expect(s).toMatchObject({ phase: 'form', draft, preview: null })
  })

  it('goes back to idle on a drop where nothing can go, and on Esc', () => {
    expect(run({ type: 'drag', kind: 'vpc', op: op('create-vpc') }, { type: 'drop', draft: null, reason: 'x' })).toEqual({ phase: 'idle', notice: 'x' })
    expect(run({ type: 'connect', source: 'rtb-1' }, { type: 'drop', draft: null, reason: null })).toEqual(IDLE)
    expect(run({ type: 'connect', source: 'rtb-1' }, { type: 'cancel' })).toEqual(IDLE)
    expect(run(...ready(), { type: 'cancel' })).toEqual(IDLE)
  })

  it('keeps only the preview of the latest edit', () => {
    let s = run(...ready(), { type: 'edit', field: 'destination', value: '10.0.0.0/8' })
    expect(s).toMatchObject({ phase: 'form', draft: { rev: 1, params: { destination: '10.0.0.0/8' } } })
    s = reduce(s, { type: 'previewed', rev: 0, preview: { ...preview, command: 'old' }, error: null })
    expect(s.phase === 'form' && s.preview?.command).toBe(preview.command)
    s = reduce(s, { type: 'previewed', rev: 1, preview: { ...preview, command: 'new' }, error: null })
    expect(s.phase === 'form' && s.preview?.command).toBe('new')
  })

  it('ignores edits to locked fields', () => {
    const s = run(...ready(), { type: 'edit', field: 'routeTableId', value: 'rtb-2' })
    expect(s.phase === 'form' && s.draft.params.routeTableId).toBe('rtb-1')
  })

  it('does not run before a preview, or while the preview has problems', () => {
    expect(run({ type: 'open', draft }, { type: 'run' }).phase).toBe('form')
    const bad = { ...preview, problems: [{ field: 'destination', message: 'no' }] }
    expect(run({ type: 'open', draft }, { type: 'previewed', rev: 0, preview: bad, error: null }, { type: 'run' }).phase).toBe('form')
  })

  it('does not run a command shown for an older edit', () => {
    const edited = run(...ready(), { type: 'edit', field: 'destination', value: '10.0.0.0/8' })
    expect(previewCurrent(edited)).toBe(false)
    expect(reduce(edited, { type: 'run' }).phase).toBe('form')
    const fresh = reduce(edited, { type: 'previewed', rev: 1, preview, error: null })
    expect(previewCurrent(fresh)).toBe(true)
    expect(reduce(fresh, { type: 'run' }).phase).toBe('running')
  })

  it('does not rerun a failed command after an edit until the new preview arrives', () => {
    const o = outcome({ exitCode: 254, stderr: 'boom', expect: null })
    const failed = run(...ready(), { type: 'run' }, { type: 'ran', outcome: o, graph: g, now: 0 })
    const edited = reduce(failed, { type: 'edit', field: 'destination', value: '10.0.0.0/8' })
    expect(reduce(edited, { type: 'run' }).phase).toBe('form')
  })

  it('waits for the collector after a run, then shows done', () => {
    let s = run(...ready(), { type: 'run' })
    expect(s.phase).toBe('running')
    expect(reduce(s, { type: 'cancel' }).phase).toBe('running')
    expect(reduce(s, { type: 'drag', kind: 'vpc', op: op('create-vpc') }).phase).toBe('running')
    expect(reduce(s, { type: 'open', draft }).phase).toBe('running')
    s = reduce(s, { type: 'ran', outcome: outcome(), graph: g, now: 1000 })
    expect(s).toMatchObject({ phase: 'waiting', since: 1000 })
    expect(reduce(s, { type: 'graph', graph: g }).phase).toBe('waiting')
    expect(reduce(s, { type: 'graph', graph: withEdge }).phase).toBe('done')
  })

  it('is done at once when the graph already shows the result', () => {
    expect(run(...ready(), { type: 'run' }, { type: 'ran', outcome: outcome(), graph: withEdge, now: 0 }).phase).toBe('done')
  })

  it('fails when the collector never shows the result', () => {
    const s = run(...ready(), { type: 'run' }, { type: 'ran', outcome: outcome(), graph: g, now: 1000 })
    expect(reduce(s, { type: 'tick', now: 1000 + WAIT_MS - 1 }).phase).toBe('waiting')
    const failed = reduce(s, { type: 'tick', now: 1000 + WAIT_MS })
    expect(failed).toMatchObject({ phase: 'failed', message: expect.stringContaining('collector vẫn chưa thấy') })
  })

  it('fails with the exit code when the command fails, keeping its output', () => {
    const o = outcome({ exitCode: 254, stderr: 'An error occurred (InvalidParameterValue)', expect: null })
    const s = run(...ready(), { type: 'run' }, { type: 'ran', outcome: o, graph: g, now: 0 })
    expect(s).toMatchObject({ phase: 'failed', outcome: o, message: expect.stringContaining('exit code 254') })
    // The learner can fix the form and try again.
    expect(reduce(s, { type: 'edit', field: 'destination', value: '10.0.0.0/8' }).phase).toBe('form')
  })

  it('shows why the server refused the run', () => {
    const problems = [{ field: 'destination', message: 'already has a route' }]
    const s = run(...ready(), { type: 'run' }, { type: 'refused', error: new BuilderError('Lệnh chưa chạy', 409, problems) })
    expect(s).toMatchObject({ phase: 'failed', outcome: null, preview: { problems } })
  })

  it('practices: copies the command, then waits for the graph with no timeout', () => {
    let s = run(...ready(), { type: 'practice', since: 7, known: [] })
    expect(s).toMatchObject({ phase: 'practicing', since: 7 })
    expect(reduce(s, { type: 'graph', graph: g }).phase).toBe('practicing')
    expect(reduce(s, { type: 'tick', now: Date.now() + 60 * WAIT_MS }).phase).toBe('practicing')
    expect(reduce(s, { type: 'run' }).phase).toBe('practicing')
    s = reduce(s, { type: 'graph', graph: withEdge })
    expect(s).toMatchObject({ phase: 'done', outcome: null })
  })

  it('does not practice a stale or refused command, and lets Esc or the toggle leave practice', () => {
    expect(run({ type: 'open', draft }, { type: 'practice', since: 0, known: [] }).phase).toBe('form')
    const bad = { ...preview, problems: [{ field: 'destination', message: 'no' }] }
    expect(run({ type: 'open', draft }, { type: 'previewed', rev: 0, preview: bad, error: null }, { type: 'practice', since: 0, known: [] }).phase).toBe('form')
    const practicing = run(...ready(), { type: 'practice', since: 0, known: [] })
    expect(reduce(practicing, { type: 'cancel' })).toEqual(IDLE)
    expect(reduce(practicing, { type: 'open', draft })).toMatchObject({ phase: 'form', draft })
  })
})
