// The lab-server's builder endpoints (PRD F4). The browser only ever sends a typed op,
// `{op, params}`; the server builds the aws command, validates it and runs it.
// Requests go through Vite's /api proxy, which keeps the page's Origin for the server to check.

export type Gesture = 'create' | 'modify' | 'connect' | 'attribute' | 'delete'

export type FieldType = 'string' | 'enum' | 'boolean' | 'integer' | 'number' | 'list' | 'json' | 'blob'

// One form field of an op (builder/shapes.py `Field.describe`): from the API's input shape, or
// the hand-written op's own field. Every value travels as text; the server reads it by `type`.
export interface FieldSpec {
  name: string // the API member (PascalCase), or a hand-written op's camelCase field
  type: FieldType
  required: boolean
  label: string
  doc?: string // the API's documentation, without HTML
  choices?: string[]
  source?: 'azs' | 'images' | 'instanceTypes' // options the lab gives
  ref?: string // the kind whose node this field takes
  refBy?: 'id' | 'label'
  placeholder?: string
  multiline?: boolean
  free?: boolean // stays editable when a gesture opened the form
  advanced?: boolean // shown under "Nâng cao"
}

// One entry of the server's op catalogue (builder/catalog.py `BuilderOp.describe`).
export interface OpSpec {
  name: string
  gesture: Gesture
  title?: string
  kind?: string // the registry kind the op belongs to
  generated?: boolean // built from the botocore shape rather than a hand-written op
  fields?: FieldSpec[]
  defaults?: Params
  nameField?: string // a generated create op's field the new resource is known by
  creates?: string // palette kind made by a create op
  containers?: string[] // tray kinds a create op may be dropped on
  container?: { param: string; by: 'id' | 'label' } // the field that takes the tray
  source?: string // node kind a connect op starts from
  sourceParam?: string
  targets?: string[] // connect: node kinds it ends on; attribute/modify/delete: node kinds it acts on
  targetParam?: string
}

export const opTitle = (ops: readonly OpSpec[] | undefined, name: string): string => ops?.find((o) => o.name === name)?.title ?? name

export interface LabTask {
  id: string
  text: string
}

// One tab of the lab's local theory page (a level-2 heading and what follows it).
export interface LabTab {
  title: string
  markdown: string
}

export interface LabInfo {
  id: string
  title: string
  attempt: number
  tasks: LabTask[]
  hints: Record<string, string[]> // by task id
  content: LabTab[] | null // null: the lab has no local content/lab.md
  palette: string[]
  tags: Record<string, string>
  cidrs: string[] // the blocks the lab plans to use
  ops: OpSpec[]
  azs: string[]
  images: string[] // AMIs this machine runs natively
  instanceTypes: string[]
  userData: string // the lab's suggested UserData script
  canRun: boolean
  runBlocker: string | null // why Run is off, from the server
  chat: ChatStatus
}

// Whether the lab-server can reach an LLM for the chat (PRD F5); never the key or the URL.
export type ChatStatus = { enabled: true; model: string; format: string } | { enabled: false; missing: string[]; error?: string }

export type Params = Record<string, string>

export interface Problem {
  field: string // the field's name; "" for the op as a whole
  message: string
}

export interface Preview {
  command: string
  argv: string[]
  problems: Problem[]
  practiceExpect: PracticeExpect // what the graph shows once the learner runs the command themselves (F4.7)
}

// A security group rule as the collector shows it in `props.ingress`.
export interface IngressRule {
  protocol: string
  from?: number
  to?: number
  sources: string[]
}

// What the next graph must show for a run to count as seen by the collector (F4.5).
// `after`: the output named no id, so any graph newer than this version counts.
// `includes`: `props[prop]` is a list holding a rule like this one; `source` is looked up in `sources`.
// `gone`: a delete counts once the node has left the graph.
export type Expect =
  | { node: string; prop?: string; value?: unknown; includes?: { protocol: string; from?: number; to?: number; source: string } }
  | { edge: string }
  | { after: number }
  | { gone: string }

// Practice mode has no output to read an id from: a create counts once a resource of that kind
// with that Name shows up ("subnet" matches either subnet kind).
export type PracticeExpect = Expect | { kind: string; label: string }

export interface RunOutcome {
  command: string
  exitCode: number | null // null: stopped after the timeout
  stdout: string
  stderr: string
  durationMs: number
  expect: Expect | null
}

export class BuilderError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly problems: Problem[] = [],
  ) {
    super(message)
  }
}

// What each refusal means for the learner; the server's own detail follows when it has one.
export const STATUS_TEXT: Record<number, string> = {
  400: 'Yêu cầu hỏng',
  403: 'lab-server chỉ nhận lệnh từ web app Cloudy Labs',
  409: 'Lệnh chưa chạy',
  415: 'Yêu cầu sai định dạng',
  422: 'Thao tác không hợp lệ',
  503: 'Chưa chạy được lệnh',
}

export function errorMessage(status: number, detail: unknown, text: Record<number, string> = STATUS_TEXT): string {
  const head = text[status] ?? `lab-server trả lỗi ${status}`
  return typeof detail === 'string' && detail ? `${head}: ${detail}` : head
}

export async function request<T>(path: string, init?: RequestInit, fetcher: typeof fetch = fetch, text = STATUS_TEXT): Promise<T> {
  let res: Response
  try {
    res = await fetcher(path, init)
  } catch {
    throw new BuilderError('Không kết nối được lab-server (chạy labctl serve)', 0)
  }
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) throw new BuilderError(errorMessage(res.status, body?.detail, text), res.status, (body?.problems as Problem[] | undefined) ?? [])
  return body as T
}

const post = (op: string, params: Params): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ op, params }),
})

// null: no lab is open (`labctl start` has not run yet).
export async function fetchLab(fetcher: typeof fetch = fetch): Promise<LabInfo | null> {
  const info = await request<LabInfo | { id: null }>('/api/lab', undefined, fetcher)
  return info.id === null ? null : (info as LabInfo)
}

export const previewOp = (op: string, params: Params, fetcher: typeof fetch = fetch) => request<Preview>('/api/preview', post(op, params), fetcher)

export const runOp = (op: string, params: Params, fetcher: typeof fetch = fetch) => request<RunOutcome>('/api/run', post(op, params), fetcher)
