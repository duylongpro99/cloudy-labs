// Ties the builder's state machine to the scene: what a drag or an edge drag over the scene means
// (drop-targets.ts, connect-rules.ts), which trays to tint, where the connect handle shows, and
// the attribute buttons of the property panel.
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { resourceId, type SceneGraph } from '../graph/graph-to-scene'
import type { GraphEdge, GraphNode, ResourceGraph } from '../graph/types'
import type { PanelAction } from '../scene/property-panel'
import type { BuilderPointer, SceneBuilder } from '../scene/live-scene'
import type { LabInfo } from './builder-api'
import { connectOp, connectOpsFrom, type ConnectCheck } from './connect-rules'
import { acceptsDrop, createOpFor, dropTarget, kindLabel } from './drop-targets'
import { createDraft, fixedDraft, ingressDraft, SUBNET_KINDS } from './form-model'
import { busy, useBuilder, type Builder } from './use-builder'

export interface SceneBuilderApi extends Builder {
  scene: SceneBuilder
  startDrag: (kind: string) => void
  actionsFor: (selected: string) => PanelAction[]
}

// The first object or tray under the pointer that the edge may end on; otherwise why the nearest cannot.
function connectTarget(lab: LabInfo, nodes: Map<string, GraphNode>, edges: readonly GraphEdge[], source: GraphNode, p: BuilderPointer): (ConnectCheck & { target: string | null }) {
  const candidates = [p.object, ...p.trays.map((t) => t.node.id)].filter((id): id is string => !!id && id !== source.id)
  let first: ConnectCheck | null = null
  for (const id of candidates) {
    const node = nodes.get(id)
    if (!node) continue
    const check = connectOp(lab.ops, source, node, edges)
    if (check.ok) return { ...check, target: id }
    first ??= check
  }
  if (first) return { ...first, target: null }
  const targets = [...new Set(connectOpsFrom(lab.ops, source.kind).flatMap((o) => o.targets ?? []))].map(kindLabel).join(', ')
  return { ok: false, reason: `Thả đầu cạnh lên ${targets}`, target: null }
}

export function useSceneBuilder(graph: ResourceGraph | null, scene: SceneGraph | null, lab: LabInfo | null, selected: string | null): SceneBuilderApi {
  const builder = useBuilder(graph)
  const { state, dispatch } = builder
  const ctx = useRef({ state, graph, scene, lab })
  ctx.current = { state, graph, scene, lab }

  // The scene stops following the pointer when the graph is not ok, so a drag in progress would
  // never see its pointerup; end it instead of leaving the ghost stuck to the cursor.
  const live = !!lab && graph?.status === 'ok'
  useEffect(() => {
    if (!live) dispatch({ type: 'drop', draft: null, reason: 'Đã huỷ thao tác: cảnh mất kết nối với emulator' })
  }, [live, dispatch])

  const onPointer = useCallback((p: BuilderPointer, end: boolean) => {
    const { state: s, graph: g, scene: sc, lab: l } = ctx.current
    if (!g || !sc || !l) return
    if (s.phase === 'dragging') {
      const what = kindLabel(s.op.creates ?? s.kind)
      const check = p.inCanvas ? dropTarget(s.op, p.trays) : { ok: false as const, reason: `Kéo ${what} vào cảnh rồi thả vào chỗ được tô sáng` }
      if (!end) return dispatch({ type: 'hover', hover: check.ok ? check.tray.node.id : null, reason: check.ok ? null : check.reason })
      if (!check.ok) return dispatch({ type: 'drop', draft: null, reason: `Đã huỷ thả ${what}: ${check.reason}` })
      const t = check.tray
      dispatch({ type: 'drop', draft: createDraft(s.op, { id: t.node.id, kind: t.kind, label: t.node.label }, g, l), reason: null })
    } else if (s.phase === 'connecting') {
      const source = sc.nodesById.get(s.source)
      if (!source) return dispatch({ type: 'drop', draft: null, reason: `${s.source} không còn trong cảnh` })
      const check = connectTarget(l, sc.nodesById, g.edges, source, p)
      if (!end) return dispatch({ type: 'hover', hover: check.target, reason: check.ok ? null : check.reason })
      if (!check.ok) return dispatch({ type: 'drop', draft: null, reason: `Đã huỷ nối: ${check.reason}` })
      dispatch({ type: 'drop', draft: fixedDraft(check.op, check.params), reason: null })
    }
  }, [dispatch])

  const ops = lab?.ops ?? []
  const selectedNode = selected && scene ? scene.nodesById.get(resourceId(selected)) : undefined
  const canStartEdge = !!selectedNode && connectOpsFrom(ops, selectedNode.kind).length > 0 && !busy(state)

  let accepts: SceneBuilder['accepts'] = () => false
  if (state.phase === 'dragging') {
    const op = state.op
    accepts = (t) => acceptsDrop(op, t.kind)
  } else if (state.phase === 'connecting') {
    const kind = scene?.nodesById.get(state.source)?.kind ?? ''
    const kinds = new Set(connectOpsFrom(ops, kind).flatMap((o) => o.targets ?? []))
    accepts = (t) => kinds.has(t.kind)
  }

  const sceneBuilder: SceneBuilder = {
    mode: state.phase === 'dragging' ? 'drag' : state.phase === 'connecting' ? 'connect' : null,
    accepts,
    target: state.phase === 'dragging' || state.phase === 'connecting' ? state.hover : null,
    connectFrom: state.phase === 'connecting' ? state.source : null,
    handleFor: canStartEdge ? selectedNode!.id : null,
    onConnectStart: (id) => dispatch({ type: 'connect', source: id }),
    onPointer,
  }

  const startDrag = useCallback((kind: string) => {
    const op = createOpFor(ctx.current.lab?.ops ?? [], kind)
    if (op) dispatch({ type: 'drag', kind, op })
  }, [dispatch])

  const actionsFor = useMemo(() => (id: string): PanelAction[] => {
    const node = scene?.nodesById.get(resourceId(id))
    if (!node) return []
    const find = (name: string) => ops.find((o) => o.name === name)
    const out: PanelAction[] = []
    const dns = find('modify-vpc-attribute')
    if (node.kind === 'vpc' && dns && node.props.enableDnsHostnames !== true) {
      out.push({ id: 'action-dns-hostnames', label: 'Bật DNS hostnames', run: () => dispatch({ type: 'open', draft: fixedDraft(dns, { vpcId: node.id }) }) })
    }
    const publicIp = find('modify-subnet-attribute')
    if (SUBNET_KINDS.has(node.kind) && publicIp && node.props.mapPublicIpOnLaunch !== true) {
      out.push({ id: 'action-public-ip', label: 'Tự gán IP public', run: () => dispatch({ type: 'open', draft: fixedDraft(publicIp, { subnetId: node.id }) }) })
    }
    const ingress = find('authorize-security-group-ingress')
    if (node.kind === 'security-group' && ingress) {
      out.push({ id: 'action-add-ingress', label: 'Thêm rule inbound', run: () => dispatch({ type: 'open', draft: ingressDraft(ingress, node.id) }) })
    }
    return out
  }, [scene, ops, dispatch])

  return { ...builder, scene: sceneBuilder, startDrag, actionsFor }
}
