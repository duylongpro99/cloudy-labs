// What the scene knows about each resource kind and edge kind: the lab-server's registry
// (GET /api/registry). registry.json is a bundled copy, used until the server's arrives and by the
// gallery and benchmark; server/tests/test_app.py keeps it equal to what the server sends.
// A kind the registry does not list, or whose icon is not bundled, gets a fallback view so a graph
// from a newer server still draws: a generic block with a yellow outline.
import { FALLBACK_ICON, ICON_SVG } from '../scene/aws-objects/icons'
import bundled from './registry.json'

// block: a coloured plinth with the glyph extruded on its top face.
// tray-badge: a small tile in the near corner of a group tray, next to the tray label.
// attach-badge: a small puck sitting on the top edge of the resource it is attached to.
// outline-only: no object; the group is drawn by its tray border alone.
export type ObjectRole = 'block' | 'tray-badge' | 'attach-badge' | 'outline-only'

// attach: the source becomes a badge on the target; the others are drawn as lines.
export type EdgeStyle = 'attach' | 'route' | 'association' | 'reference' | 'replica'

export interface KindView {
  kind: string
  label: string
  service: string
  signingName?: string // what api-tap names the service (cloudwatch is `monitoring`); absent: the service
  role: ObjectRole
  category: string // colour family, see aws-objects/object-theme.ts
  icon: string | null // file under scene/aws-objects/icons; null only for outline-only kinds
  source: string | null // path in the AWS icon package; null for self-drawn artwork
  height: number | null // block height; null uses the default
  order: number // sort key for siblings in the layout
  group: boolean // drawn as a tray holding its children
  stack: boolean // a group whose child groups stack front to back instead of left to right
  host: boolean // attach badges may sit on it
  actions: string[] // API nouns (e.g. "Vpc" in CreateVpc) that fly to this kind
  curveSegments: number | null // Bezier subdivision when extruding the glyph
  parents: string[]
  floci: string
  fallback?: boolean // not fully supported by this build of the web app
}

export interface EdgeKindView {
  kind: string
  style: EdgeStyle
}

export interface RegistryData {
  kinds: KindView[]
  edgeKinds: EdgeKindView[]
}

const FALLBACK_ORDER = 1000

interface Index {
  data: RegistryData
  kinds: Map<string, KindView>
  edges: Map<string, EdgeStyle>
  nouns: { noun: string; kind: string; signing: string }[] // longest noun first
}

function index(data: RegistryData): Index {
  const nouns = data.kinds.flatMap((k) => k.actions.map((noun) => ({ noun, kind: k.kind, signing: k.signingName ?? k.service })))
  return {
    data,
    kinds: new Map(data.kinds.map((k) => [k.kind, k])),
    edges: new Map(data.edgeKinds.map((e) => [e.kind, e.style])),
    nouns: nouns.sort((a, b) => b.noun.length - a.noun.length),
  }
}

let current = index(bundled as RegistryData)
const fallbacks = new Map<string, KindView>()

// Checks the shape only as far as the scene relies on it; anything else is the server's contract.
export function parseRegistry(json: unknown): RegistryData {
  const r = json as Partial<RegistryData> | null
  if (!r || typeof r !== 'object' || !Array.isArray(r.kinds) || !Array.isArray(r.edgeKinds)) throw new Error('registry: missing "kinds" or "edgeKinds"')
  for (const k of r.kinds) if (typeof k?.kind !== 'string' || typeof k.role !== 'string') throw new Error('registry: a kind without "kind" or "role"')
  return r as RegistryData
}

export function setRegistry(data: RegistryData) {
  current = index(data)
  fallbacks.clear()
}

export const registryData = () => current.data

export function kindView(kind: string): KindView {
  const known = current.kinds.get(kind)
  if (known && (known.role === 'outline-only' || (known.icon && ICON_SVG.has(known.icon)))) return known
  let f = fallbacks.get(kind)
  if (!f) {
    f = known
      ? { ...known, role: known.role === 'outline-only' ? 'block' : known.role, icon: FALLBACK_ICON, source: null, curveSegments: null, fallback: true }
      : {
          kind, label: kind, service: '', role: 'block', category: 'general', icon: FALLBACK_ICON, source: null, height: null,
          order: FALLBACK_ORDER, group: false, stack: false, host: false, actions: [], curveSegments: null, parents: [], floci: 'unknown', fallback: true,
        }
    fallbacks.set(kind, f)
  }
  return f
}

// The palette's "subnet" becomes public or private by its route table.
const LABEL_ALIAS: Record<string, string> = { subnet: 'Subnet' }

export const kindLabel = (kind: string) => LABEL_ALIAS[kind] ?? kindView(kind).label

// An edge kind the registry does not list is drawn as a plain reference.
export const edgeStyleOf = (kind: string): EdgeStyle => current.edges.get(kind) ?? 'reference'

// The kinds an API action names: the longest noun the action contains wins, so "CreateDBInstance"
// picks a DBInstance kind over an Instance kind. With the service api-tap reported, only that
// service's kinds count: ec2 CreateRoute is a route table's, apigateway CreateRoute an HTTP API's.
export function actionKinds(action: string, service?: string): string[] {
  const nouns = service === undefined ? current.nouns : current.nouns.filter((n) => n.signing === service)
  const noun = nouns.find((n) => action.includes(n.noun))?.noun
  return noun === undefined ? [] : [...new Set(nouns.filter((n) => n.noun === noun).map((n) => n.kind))]
}
