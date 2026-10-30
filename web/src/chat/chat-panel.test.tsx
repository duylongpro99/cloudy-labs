import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LabInfo } from '../builder/builder-api'
import { LAB } from '../builder/test-fixtures'
import { THEMES } from '../scene/theme'
import type { ChatReply } from './chat-api'
import { ChatPanel } from './chat-panel'
import { EMPTY, type Chat, type ChatState } from './use-chat'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const REPLY: ChatReply = {
  reply: 'Hai bước',
  refusal: null,
  steps: [
    { op: 'create-vpc', params: { name: 'v' }, explanation: 'thiếu cidr', command: '', problems: [{ field: 'cidr', message: 'this parameter is missing' }], deferred: false, refs: [], practiceExpect: null },
    { op: 'create-internet-gateway', params: { name: 'igw2' }, explanation: 'cổng ra internet', command: 'aws ec2 create-internet-gateway', problems: [], deferred: false, refs: [], practiceExpect: null },
    { op: 'attach-internet-gateway', params: { igwId: { ref: 2 }, vpcId: 'vpc-1' }, explanation: 'gắn', command: "aws ec2 attach-internet-gateway --internet-gateway-id '<id từ bước 2>'", problems: [], deferred: true, refs: [2], practiceExpect: null },
  ],
}
const ANSWERED: ChatState = { ...EMPTY, turns: [{ role: 'user', text: 'cho VPC ra internet' }, { role: 'assistant', reply: REPLY }], runs: REPLY.steps.map(() => ({ status: 'pending' })) }

describe('ChatPanel', () => {
  let root: Root
  let host: HTMLElement
  let chat: Chat
  const render = (state: ChatState, lab: LabInfo = LAB, extra: { practice?: boolean; builderBusy?: boolean } = {}) => {
    chat = { state, ask: vi.fn(), run: vi.fn(), runAll: vi.fn() }
    act(() => root.render(<ChatPanel chat={chat} lab={lab} practice={extra.practice ?? false} onPractice={() => {}} builderBusy={extra.builderBusy ?? false} theme={THEMES.light} />))
  }
  const q = <T extends Element = HTMLElement>(sel: string) => host.querySelector(sel) as T | null
  const runButtons = () => [...host.querySelectorAll<HTMLButtonElement>('.run-step')]

  beforeEach(() => {
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
  })

  it('explains how to turn the chat on and names what is missing', () => {
    render(EMPTY, { ...LAB, chat: { enabled: false, missing: ['LLM_API_KEY', 'LLM_MODEL'] } })
    expect(q('#chat-setup')?.textContent).toContain('~/.cloudy-labs/llm.env')
    expect(q('#chat-missing')?.textContent).toBe('Còn thiếu: LLM_API_KEY, LLM_MODEL')
    expect(q('#chat-input')).toBeNull()
  })

  it('shows each step and only lets a sound step run', () => {
    render(ANSWERED)
    const [broken, ok, deferred] = runButtons()
    expect(broken.disabled).toBe(true)
    expect(host.querySelector('.step-problems')?.textContent).toContain('cidr: this parameter is missing')
    expect(ok.disabled).toBe(false)
    expect(host.querySelectorAll('.step-deferred')).toHaveLength(1)
    expect(deferred.closest('li')?.querySelector('.step-command')?.textContent).toContain('<id từ bước 2>')
    act(() => ok.click())
    expect(chat.run).toHaveBeenCalledWith(1)
    act(() => q<HTMLButtonElement>('#run-all')!.click())
    expect(chat.runAll).toHaveBeenCalled()
  })

  it('turns Run off while the builder runs or the server cannot run commands', () => {
    render(ANSWERED, LAB, { builderBusy: true })
    expect(runButtons().every((b) => b.disabled)).toBe(true)
    expect(q<HTMLButtonElement>('#run-all')!.disabled).toBe(true)
    render(ANSWERED, { ...LAB, canRun: false, runBlocker: 'the aws CLI is not installed' })
    expect(runButtons()[1].disabled).toBe(true)
    expect(host.textContent).toContain('the aws CLI is not installed')
  })

  it('offers Chép instead of Run in practice mode, even when the server cannot run commands', () => {
    render(ANSWERED, { ...LAB, canRun: false, runBlocker: 'no aws' }, { practice: true })
    expect(runButtons()[1].textContent).toBe('Chép')
    expect(runButtons()[1].disabled).toBe(false)
    expect(q('#run-all')).toBeNull()
  })

  it('shows a refusal as a message labelled out of scope', () => {
    render({ ...EMPTY, turns: [{ role: 'user', text: 'tạo S3 bucket' }, { role: 'assistant', reply: { reply: 'Hãy làm VPC.', refusal: 'S3 không có trong lab này', steps: [] } }] })
    expect(q('.chat-refusal')?.textContent).toBe('Ngoài phạm vi S3 không có trong lab này')
    expect(runButtons()).toHaveLength(0)
  })

  it('sends on Enter and keeps Shift+Enter for a new line', () => {
    render(EMPTY)
    const input = q<HTMLTextAreaElement>('#chat-input')!
    const type = (value: string) => {
      const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!
      act(() => {
        set.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    }
    type('tạo subnet')
    act(() => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true })))
    expect(chat.ask).not.toHaveBeenCalled()
    act(() => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    expect(chat.ask).toHaveBeenCalledWith('tạo subnet')
  })
})
