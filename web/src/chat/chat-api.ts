// The lab-server's chat endpoint (PRD F5). The server asks the model, builds each suggested step's
// command with the builder's own code and validates it; nothing runs until the learner presses Run.
import { STATUS_TEXT, request, type PracticeExpect, type Problem } from '../builder/builder-api'

// `{ref: n}`: the id the create step n (1-based) of the same answer makes, filled in once it ran.
export type Ref = { ref: number }
export type StepParams = Record<string, string | Ref>

export interface ChatStep {
  op: string
  params: StepParams
  explanation: string
  command: string // "" when no command can be built; refs show as <id từ bước n>
  problems: Problem[]
  deferred: boolean // uses an id an earlier step makes: checked against the graph when it runs
  refs: number[]
  practiceExpect: PracticeExpect | null
}

export interface ChatReply {
  reply: string
  refusal: string | null // why the request is outside the lab or the emulator
  steps: ChatStep[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

// Mirrors the server's limits on what it accepts.
export const CHAT_TURNS_MAX = 12
export const CHAT_TURN_CHARS_MAX = 8000

const CHAT_TEXT: Record<number, string> = {
  ...STATUS_TEXT,
  409: 'Chưa hỏi được',
  422: 'Câu hỏi không gửi được',
  502: 'Model không trả lời được',
  503: 'Chưa hỏi được',
}

export const sendChat = (messages: ChatMessage[], fetcher: typeof fetch = fetch) =>
  request<ChatReply>(
    '/api/chat',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages }) },
    fetcher,
    CHAT_TEXT,
  )
