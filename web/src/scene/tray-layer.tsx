// Nested translucent trays for Region / VPC / AZ / Subnet with AWS group border colours.
// Groups with a tray badge get their label moved right to sit beside the badge.
// New trays fade in and removed trays fade out; frames are requested only while a fade runs.
// A ghost tray (part of the lab's target not built yet) is fainter, always dashed and labelled
// "mục tiêu"; a real tray that reached its target node carries the achieved mark before its label.
import { Line, Text } from '@react-three/drei'
import { useFrame, useThree, type ThreeElements } from '@react-three/fiber'
import { memo, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Mesh, MeshStandardMaterial } from 'three'
import type { Line2 } from 'three/examples/jsm/lines/Line2.js'
import type { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { MANIFEST_BY_KIND, TRAY_LABEL_FROM_NEAR_EDGE, TRAY_LABEL_INSET, TRAY_LABEL_SHIFT } from './aws-objects'
import { FADE_CURVE, Presence } from './aws-objects/entrance'
import type { LaidOutGroup } from './layout'
import { TRAY_H } from './layout'
import type { Theme } from './theme'

export const FONT = '/fonts/BeVietnamPro-Medium.woff'

const CHAR_WIDTH = 0.6 // average glyph advance of the label font, in em

// Shortens a label that would run past its tray's edge, e.g. long generated subnet names.
function fitLabel(text: string, width: number, fontSize: number) {
  const max = Math.max(4, Math.floor(width / (fontSize * CHAR_WIDTH)))
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

// Sets a tray's opacity factor, 0..1.
type Fade = (f: number) => void
// troika-three-text's Text: opacities are read on every render, so no re-sync is needed.
interface TroikaText {
  fillOpacity: number
  outlineOpacity: number
}

// A tick drawn as a line, so it does not depend on the label font having a check-mark glyph.
const TICK: [number, number, number][] = [
  [-0.5, 0, 0],
  [-0.15, -0.38, 0],
  [0.5, 0.42, 0],
]
export const ACHIEVED_SIZE = 0.55

export function AchievedMark({ theme, size = ACHIEVED_SIZE, ...props }: { theme: Theme; size?: number } & ThreeElements['group']) {
  return (
    <group {...props} scale={size} userData={{ achieved: true }}>
      <Line points={TICK} color={theme.achieved} lineWidth={3} />
    </group>
  )
}

function Tray({ g, theme, register }: { g: LaidOutGroup; theme: Theme; register: (id: string, fade: Fade) => () => void }) {
  const ghost = !!g.node.ghost
  const base = theme.groups[g.kind]
  const style = ghost ? { ...base, dashed: 'dash' as const, opacity: base.opacity * theme.ghost.trayOpacity } : base
  const borderOpacity = ghost ? theme.ghost.borderOpacity : 1
  const mesh = useRef<Mesh>(null)
  const line = useRef<Line2>(null)
  const text = useRef<TroikaText>(null)
  useLayoutEffect(
    () =>
      register(g.node.id, (f) => {
        if (mesh.current) (mesh.current.material as MeshStandardMaterial).opacity = style.opacity * f
        if (line.current) (line.current.material as LineMaterial).opacity = borderOpacity * f
        if (text.current) text.current.fillOpacity = text.current.outlineOpacity = f
      }),
    [register, g.node.id, style.opacity, borderOpacity],
  )
  const top = g.y + TRAY_H + 0.01
  // Stable points: drei Line rebuilds its geometry whenever the points array changes.
  const corners = useMemo<[number, number, number][]>(
    () => [
      [g.x, top, g.z],
      [g.x + g.w, top, g.z],
      [g.x + g.w, top, g.z + g.d],
      [g.x, top, g.z + g.d],
      [g.x, top, g.z],
    ],
    [g.x, g.z, g.w, g.d, top],
  )
  // Line2 has no dash-dot pattern; a long dash with a short gap stands in for it.
  const dash = style.dashed === 'dash' ? { dashSize: 0.5, gapSize: 0.35 } : { dashSize: 1.4, gapSize: 0.3 }
  const fontSize = g.kind === 'region' || g.kind === 'vpc' ? 0.75 : 0.55
  const markX = g.x + TRAY_LABEL_INSET + (MANIFEST_BY_KIND[g.kind].role === 'tray-badge' ? TRAY_LABEL_SHIFT : 0)
  const labelX = markX + (g.node.achieved ? fontSize * 1.3 : 0)
  const labelZ = g.z + g.d - TRAY_LABEL_FROM_NEAR_EDGE
  const label = fitLabel(ghost ? `${g.node.label} · mục tiêu` : g.node.label, g.x + g.w - labelX - TRAY_LABEL_INSET, fontSize)
  return (
    <group>
      <mesh
        ref={mesh}
        position={[g.x + g.w / 2, g.y + TRAY_H / 2, g.z + g.d / 2]}
        renderOrder={g.level}
        receiveShadow={!ghost}
        userData={{ treatAsOpaque: true, ghost }}
        // N8AO would otherwise skip transparent trays and leave blocks floating.
      >
        <boxGeometry args={[g.w, TRAY_H, g.d]} />
        <meshStandardMaterial color={style.fill} transparent opacity={style.opacity} depthWrite={false} roughness={0.9} metalness={0} />
      </mesh>
      <Line
        ref={line}
        points={corners}
        transparent
        color={style.border}
        lineWidth={g.kind === 'region' || g.kind === 'vpc' ? 2.4 : 1.8}
        dashed={style.dashed !== 'none'}
        {...(style.dashed !== 'none' ? dash : {})}
        renderOrder={g.level + 0.5}
      />
      <Text
        ref={text}
        font={FONT}
        fontSize={fontSize}
        color={ghost ? theme.ghost.label : theme.label}
        outlineWidth={0.04}
        outlineColor={theme.labelOutline}
        anchorX="left"
        anchorY="middle"
        rotation={[-Math.PI / 2, 0, 0]}
        position={[labelX, top + 0.005, labelZ]}
        renderOrder={g.level + 0.6}
      >
        {label}
      </Text>
      {g.node.achieved && (
        <AchievedMark theme={theme} size={fontSize} position={[markX + fontSize * 0.5, top + 0.01, labelZ]} rotation={[-Math.PI / 2, 0, 0]} />
      )}
    </group>
  )
}

interface TrayItem {
  id: string
  g: LaidOutGroup
}

// Memoised so hover and selection changes in the scene do not re-render every tray.
export const TrayLayer = memo(function TrayLayer({ groups, theme, animate = true }: { groups: LaidOutGroup[]; theme: Theme; animate?: boolean }) {
  const presence = useRef(new Presence<TrayItem>(FADE_CURVE)).current
  const fades = useRef(new Map<string, Fade>()).current
  const running = useRef(false)
  const invalidate = useThree((s) => s.invalidate)
  // Bumped when finished fade-outs are dropped, so they stop being drawn.
  const [pruned, setPruned] = useState(0)
  const shown = useMemo(() => {
    const items = groups.map((g) => ({ id: g.node.id, g }))
    presence.update(items, performance.now(), animate)
    return [...items, ...presence.exiting()]
    // `pruned` only forces the regrouping.
  }, [groups, presence, animate, pruned])

  // Applies every tray's current opacity; true once no fade is left.
  const apply = (now: number) => {
    let done = true
    for (const [id, fade] of fades) {
      const v = presence.get(id, now) ?? { value: 0, done: true }
      fade(v.value)
      if (!v.done) done = false
    }
    return done
  }
  const register = useMemo(
    () => (id: string, fade: Fade) => {
      fades.set(id, fade)
      fade(presence.get(id, performance.now())?.value ?? 0)
      return () => void (fades.get(id) === fade && fades.delete(id))
    },
    [fades, presence],
  )
  useLayoutEffect(() => {
    running.current = true
    invalidate()
  }, [shown, invalidate])
  useFrame(() => {
    if (!running.current) return
    const now = performance.now()
    if (!apply(now)) return invalidate()
    running.current = false
    if (presence.prune(now)) setPruned((n) => n + 1)
  })

  return (
    <group>
      {shown.map(({ id, g }) => (
        <Tray key={id} g={g} theme={theme} register={register} />
      ))}
    </group>
  )
})
