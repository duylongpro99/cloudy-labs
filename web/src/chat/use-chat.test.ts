// The chat's runs through the real hook, with the lab-server faked at the API module.
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../builder/builder-api'
import { LAB, golden } from '../builder/test-fixtures'
import { WAIT_MS } from '../builder/use-builder'
import type { GraphNode, ResourceGraph } from '../graph/types'
import * as chatApi from './chat-api'
import { EMPTY, history, reduce, resolveParams, useChat, type Chat, type ChatTurn } from './use-chat'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const VPC = 'vpc-149d0439'
const step = (op: string, params: chatApi.StepParams, extra: Partial<chatApi.ChatStep> = {}): chatApi.ChatStep => ({
  op,
  params,
  explanation: 'why',
  command: `aws ec2 ${op}`,
  problems: [],
  deferred: Object.values(params).some((v) => typeof v !== 'string'),
  refs: [],
  practiceExpect: null,
  ...extra,
})
const TWO: chatApi.ChatReply = {
  reply: 'Two steps',
  refusal: null,
  steps: [step('create-internet-gateway', { name: 'igw2' }), step('attach-internet-gateway', { igwId: { ref: 1 }, vpcId: VPC })],
}
const outcome = (expect: api.Expect | null, exitCode: number | null = 0): api.RunOutcome => ({ command: 'aws', exitCode, stdout: '', stderr: exitCode ? 'boom' : '', durationMs: 5, expect })
const preview = (command: string, practiceExpect: api.PracticeExpect = { after: 0 }): api.Preview => ({ command, argv: [], problems: [], practiceExpect })
const igw = (id: string): GraphNode => ({ id, kind: 'igw', label: 'igw2', props: {} })
const withNodes = (g: ResourceGraph, ...nodes: GraphNode[]): ResourceGraph => ({ ...g, version: g.version + 1, nodes: [...g.nodes, ...nodes] })

let chat: Chat
function Harness({ graph, practice = false }: { graph: ResourceGraph; practice?: boolean }) {
  chat = useChat(graph, LAB, practice)
  return null
}

describe('useChat', () => {
  let root: Root
  let host: HTMLElement
  const render = (graph: ResourceGraph, practice = false) => act(() => root.render(createElement(Harness, { graph, practice })))
  const answer = async (reply: chatApi.ChatReply) => {
    vi.spyOn(chatApi, 'sendChat').mockResolvedValue(reply)
    await act(async () => chat.ask('help'))
  }

  beforeEach(() => {
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('runs a chain in order and fills in the id the first step made', async () => {
    const g = golden()
    vi.spyOn(api, 'previewOp').mockImplementation(async (op, params) => preview(`${op} ${JSON.stringify(params)}`))
    const runOp = vi.spyOn(api, 'runOp').mockResolvedValueOnce(outcome({ node: 'igw-new' })).mockResolvedValueOnce(outcome(null))
    render(g)
    await answer(TWO)
    expect(chat.state.runs.map((r) => r.status)).toEqual(['pending', 'pending'])

    await act(async () => chat.runAll())
    expect(chat.state.runs[0]).toMatchObject({ status: 'waiting' }) // the scene does not show igw-new yet
    expect(runOp).toHaveBeenCalledTimes(1)

    render(withNodes(g, igw('igw-new')))
    await act(async () => {})
    expect(chat.state.runs[0]).toMatchObject({ status: 'done', id: 'igw-new' })
    expect(runOp.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ['create-internet-gateway', { name: 'igw2' }],
      ['attach-internet-gateway', { igwId: 'igw-new', vpcId: VPC }],
    ])
    expect(chat.state.runs[1]).toMatchObject({ status: 'done', command: expect.stringContaining('igw-new') })
    expect(chat.state.chain).toBe(false)
  })

  it('stops the chain at the first failure', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview('aws ec2 create-internet-gateway'))
    const runOp = vi.spyOn(api, 'runOp').mockResolvedValue(outcome(null, 254))
    render(golden())
    await answer(TWO)
    await act(async () => chat.runAll())
    expect(chat.state.runs[0]).toMatchObject({ status: 'failed', message: expect.stringContaining('exit code 254') })
    expect(chat.state.runs[1].status).toBe('pending')
    expect(runOp).toHaveBeenCalledTimes(1)
    expect(chat.state.chain).toBe(false)
  })

  it('will not run a step before the step whose id it uses', async () => {
    const runOp = vi.spyOn(api, 'runOp')
    render(golden())
    await answer(TWO)
    await act(async () => chat.run(1))
    expect(chat.state.runs[1]).toMatchObject({ status: 'failed', message: expect.stringContaining('Chạy bước 1 trước') })
    expect(runOp).not.toHaveBeenCalled()
  })

  it('shows a refused run as failed with the server problems', async () => {
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview('aws ec2 create-internet-gateway'))
    vi.spyOn(api, 'runOp').mockRejectedValue(new api.BuilderError('Lệnh chưa chạy: another command is running', 409, [{ field: '', message: 'busy' }]))
    render(golden())
    await answer(TWO)
    await act(async () => chat.run(0))
    expect(chat.state.runs[0]).toMatchObject({ status: 'failed', message: expect.stringContaining('another command'), problems: [{ field: '', message: 'busy' }] })
  })

  it('never runs a step the server found wrong', async () => {
    const previewOp = vi.spyOn(api, 'previewOp')
    render(golden())
    await answer({ ...TWO, steps: [step('create-vpc', { name: 'v' }, { problems: [{ field: 'cidr', message: 'this parameter is missing' }] })] })
    await act(async () => chat.run(0))
    expect(chat.state.runs[0]).toMatchObject({ status: 'failed', problems: [{ field: 'cidr' }] })
    expect(previewOp).not.toHaveBeenCalled()
  })

  it('gives up once the scene never shows the run', async () => {
    vi.useFakeTimers()
    vi.spyOn(api, 'previewOp').mockResolvedValue(preview('aws ec2 create-internet-gateway'))
    vi.spyOn(api, 'runOp').mockResolvedValue(outcome({ node: 'igw-new' }))
    render(golden())
    await answer(TWO)
    await act(async () => chat.run(0))
    expect(chat.state.runs[0].status).toBe('waiting')
    await act(async () => vi.advanceTimersByTimeAsync(WAIT_MS + 1))
    expect(chat.state.runs[0]).toMatchObject({ status: 'failed', message: expect.stringContaining('collector') })
  })

  it('in practice mode copies instead of running, and takes the id from the graph', async () => {
    const g = withNodes(golden(), igw('igw-old')) // the same Name made before the copy does not count
    vi.spyOn(api, 'previewOp').mockImplementation(async (op, params) =>
      preview(`${op} ${JSON.stringify(params)}`, op === 'create-internet-gateway' ? { kind: 'igw', label: 'igw2' } : { edge: 'attach:igw-new->vpc' }),
    )
    const runOp = vi.spyOn(api, 'runOp')
    render(g, true)
    await answer(TWO)
    await act(async () => chat.run(0))
    expect(chat.state.runs[0]).toMatchObject({ status: 'practicing', known: expect.arrayContaining(['igw-old']) })

    render({ ...g, version: g.version + 1 }, true)
    expect(chat.state.runs[0].status).toBe('practicing')
    render(withNodes(g, igw('igw-new')), true)
    expect(chat.state.runs[0]).toMatchObject({ status: 'done', id: 'igw-new' })

    await act(async () => chat.run(1))
    expect(chat.state.runs[1]).toMatchObject({ status: 'practicing', command: expect.stringContaining('igw-new') })
    expect(runOp).not.toHaveBeenCalled()
  })

  it('forgets the conversation when the lab attempt changes', async () => {
    let lab = LAB
    function Lab() {
      chat = useChat(golden(), lab, false)
      return null
    }
    act(() => root.render(createElement(Lab)))
    await answer(TWO)
    expect(chat.state.turns).toHaveLength(2)
    lab = { ...LAB, attempt: LAB.attempt + 1 }
    act(() => root.render(createElement(Lab)))
    expect(chat.state).toEqual(EMPTY)
  })

  it('runs nothing when the lab is reset while the preview is out', async () => {
    let lab = LAB
    let previewed: (p: api.Preview) => void = () => {}
    vi.spyOn(api, 'previewOp').mockReturnValue(new Promise((resolve) => (previewed = resolve)))
    const runOp = vi.spyOn(api, 'runOp')
    function Lab() {
      chat = useChat(golden(), lab, false)
      return null
    }
    act(() => root.render(createElement(Lab)))
    await answer(TWO)
    await act(async () => void chat.run(0))
    lab = { ...LAB, attempt: LAB.attempt + 1 }
    act(() => root.render(createElement(Lab)))
    await act(async () => previewed(preview('aws ec2 create-internet-gateway')))
    expect(runOp).not.toHaveBeenCalled()
    expect(chat.state).toEqual(EMPTY)
  })

  it('shows why the question was not answered', async () => {
    vi.spyOn(chatApi, 'sendChat').mockRejectedValue(new api.BuilderError('Model không trả lời được: timeout', 502))
    render(golden())
    await act(async () => chat.ask('help'))
    expect(chat.state).toMatchObject({ asking: false, error: 'Model không trả lời được: timeout' })
  })
})

describe('chat helpers', () => {
  it('resolves refs only from done steps that made an id', () => {
    const s = TWO.steps[1]
    expect(resolveParams(s, [{ status: 'done', command: '', id: 'igw-9' }])).toEqual({ igwId: 'igw-9', vpcId: VPC })
    expect(resolveParams(s, [{ status: 'pending' }])).toContain('Chạy bước 1 trước')
    expect(resolveParams(s, [{ status: 'done', command: '' }])).toContain('không cho id')
  })

  it('sends the last turns, answers as words and op names', () => {
    const turns: ChatTurn[] = Array.from({ length: 14 }, (_, i): ChatTurn => (i % 2 ? { role: 'assistant', reply: TWO } : { role: 'user', text: `q${i}` }))
    turns.push({ role: 'user', text: 'last' })
    const sent = history(turns)
    expect(sent).toHaveLength(chatApi.CHAT_TURNS_MAX - 1) // never opens with an answer: some providers refuse that
    expect(sent[0].role).toBe('user')
    expect(sent.at(-1)).toEqual({ role: 'user', content: 'last' })
    expect(sent.at(-2)?.content).toBe('Two steps\nCác bước: create-internet-gateway, attach-internet-gateway')
    expect(history([{ role: 'user', text: 'S3?' }, { role: 'assistant', reply: { reply: ' ', refusal: 'S3', steps: [] } }])[1].content).toBe('Ngoài phạm vi: S3')
  })

  it('keeps a run of the old answer from touching the new one', () => {
    const s = reduce(reduce({ ...EMPTY, asking: true }, { type: 'answered', reply: TWO }), { type: 'ran', step: 0, outcome: outcome(null), graph: null, now: 0 })
    expect(s.runs[0].status).toBe('pending')
  })
})
