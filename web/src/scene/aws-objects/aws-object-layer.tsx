// Draws any number of AWS objects with two InstancedMeshes per kind (plinth and glyph),
// so draw calls grow with the number of kinds, not the number of objects.
// Entrance: each instance scales up from its base, staggered, updated in useFrame only while it runs.
import type { ThreeEvent } from '@react-three/fiber'
import { useFrame, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { Matrix4, Quaternion, Vector3, type InstancedMesh } from 'three'
import { ENTRANCE_MS, entranceDelays, entranceScale } from './entrance'
import { glyphGeometry, plinthGeometry } from './geometry-cache'
import { HighlightOverlay } from './highlight-overlay'
import type { AwsKind } from './manifest'
import { MANIFEST_BY_KIND } from './manifest'
import { GLYPH_COVERAGE, plinthShape, type Vec3 } from './object-specs'
import { OBJECT_THEMES, type ThemeName } from './object-theme'

export interface AwsObjectPlacement {
  id: string
  kind: AwsKind
  position: Vec3 // centre of the object's base
}

export interface AwsObjectLayerProps {
  placements: readonly AwsObjectPlacement[]
  theme: ThemeName
  coverage?: number
  animate?: boolean
  shadows?: boolean
  hovered?: string | null
  selected?: string | null
  outlineColor?: string
  onHover?: (id: string | null) => void
  onSelect?: (id: string) => void
  // Called once every object has reached full size, e.g. to refresh a static shadow map.
  onSettled?: () => void
}

const noRaycast = () => {}

function KindBatch({ kind, items, shown, theme, coverage, animate, shadows, onHover, onSelect, onSettled }: {
  kind: AwsKind
  items: readonly AwsObjectPlacement[]
  shown: ReadonlySet<string> // ids that already finished their entrance; they stay at full size
  theme: ThemeName
  coverage: number
  animate: boolean
  shadows: boolean
  onHover?: (id: string | null) => void
  onSelect?: (id: string) => void
  onSettled: (kind: AwsKind) => void
}) {
  const plinth = useRef<InstancedMesh>(null)
  const glyph = useRef<InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const shape = plinthShape(kind)
  const palette = OBJECT_THEMES[theme][MANIFEST_BY_KIND[kind].category]
  const anim = useRef({ start: 0, running: false })
  const settledRef = useRef(onSettled)
  settledRef.current = onSettled

  const write = useMemo(() => {
    const m = new Matrix4()
    const q = new Quaternion()
    const pos = new Vector3()
    const scl = new Vector3()
    const glyphSide = shape.side * coverage
    // Read once per item list, so ids marked shown while this list animates keep their own timing.
    const delays = entranceDelays(
      items.map((it) => it.id),
      animate ? shown : new Set(items.map((it) => it.id)),
    )
    return (elapsedMs: number) => {
      const p = plinth.current
      const g = glyph.current
      if (!p || !g) return true
      let settled = true
      items.forEach((it, i) => {
        const delay = delays[i]
        const t = delay === null ? 1 : (elapsedMs - delay) / ENTRANCE_MS
        if (t < 1) settled = false
        const k = entranceScale(t)
        const [x, y, z] = it.position
        p.setMatrixAt(i, m.compose(pos.set(x, y, z), q, scl.setScalar(k)))
        g.setMatrixAt(i, m.compose(pos.set(x, y + shape.height * k, z), q, scl.setScalar(glyphSide * k)))
      })
      p.instanceMatrix.needsUpdate = true
      g.instanceMatrix.needsUpdate = true
      // Bounds feed raycasting and culling; recompute once the final size is known.
      p.computeBoundingSphere()
      g.computeBoundingSphere()
      return settled
    }
  }, [items, shown, animate, coverage, shape.side, shape.height])

  useLayoutEffect(() => {
    anim.current = { start: performance.now(), running: true }
    anim.current.running = !write(0)
    if (!anim.current.running) settledRef.current(kind)
    invalidate()
  }, [write, invalidate, kind])

  useFrame(() => {
    const a = anim.current
    if (!a.running) return
    a.running = !write(performance.now() - a.start)
    if (!a.running) settledRef.current(kind)
    invalidate()
  })

  const handlers = onHover || onSelect
    ? {
        onPointerMove: (e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation()
          if (e.instanceId !== undefined) onHover?.(items[e.instanceId].id)
        },
        onPointerOut: () => onHover?.(null),
        onClick: (e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          if (e.instanceId !== undefined) onSelect?.(items[e.instanceId].id)
        },
      }
    : {}

  return (
    <>
      <instancedMesh
        ref={plinth}
        args={[plinthGeometry(kind), undefined, items.length]}
        castShadow={shadows}
        receiveShadow={shadows}
        userData={{ awsKind: kind, part: 'plinth' }}
        {...handlers}
      >
        <meshStandardMaterial color={palette.plinth} roughness={0.75} metalness={0} />
      </instancedMesh>
      {/* The glyph is not raycast: a pick passes through it to the plinth underneath. */}
      <instancedMesh
        ref={glyph}
        args={[glyphGeometry(kind), undefined, items.length]}
        castShadow={shadows}
        raycast={noRaycast}
        userData={{ awsKind: kind, part: 'glyph' }}
      >
        <meshStandardMaterial color={palette.glyph} roughness={0.55} metalness={0} />
      </instancedMesh>
    </>
  )
}

export function AwsObjectLayer({
  placements,
  theme,
  coverage = GLYPH_COVERAGE,
  animate = true,
  shadows = true,
  hovered = null,
  selected = null,
  outlineColor = '#0972D3',
  onHover,
  onSelect,
  onSettled,
}: AwsObjectLayerProps) {
  // Ids that finished their entrance. Only ids new to the layer animate when placements change;
  // removed ids are forgotten so they animate again if they come back.
  const shown = useRef(new Set<string>()).current
  const byKind = useMemo(() => {
    const groups = new Map<AwsKind, AwsObjectPlacement[]>()
    for (const p of placements) {
      if (MANIFEST_BY_KIND[p.kind].role === 'outline-only') continue
      groups.set(p.kind, [...(groups.get(p.kind) ?? []), p])
    }
    const present = new Set(placements.map((p) => p.id))
    for (const id of shown) if (!present.has(id)) shown.delete(id)
    return [...groups]
  }, [placements, shown])
  // Only drawable placements: an outline-only id has no plinth to highlight.
  const byId = useMemo(() => new Map(byKind.flatMap(([, items]) => items.map((p) => [p.id, p] as const))), [byKind])

  // Kinds that reached full size since the batches last changed; a new set per batch list.
  const settled = useMemo(() => new Set<AwsKind>(), [byKind])
  const onSettledRef = useRef(onSettled)
  onSettledRef.current = onSettled
  const batchSettled = useCallback(
    (kind: AwsKind) => {
      if (settled.has(kind)) return
      settled.add(kind)
      for (const p of byKind.find(([k]) => k === kind)?.[1] ?? []) shown.add(p.id)
      if (settled.size === byKind.length) onSettledRef.current?.()
    },
    [settled, byKind, shown],
  )
  useEffect(() => {
    if (byKind.length === 0) onSettledRef.current?.()
  }, [byKind])
  const hoverTarget = hovered && hovered !== selected ? byId.get(hovered) : undefined
  const selectTarget = selected ? byId.get(selected) : undefined

  return (
    <group>
      {byKind.map(([kind, items]) => (
        // Remount when the count changes: an InstancedMesh's capacity is fixed at creation.
        <KindBatch
          key={`${kind}-${items.length}`}
          kind={kind}
          items={items}
          shown={shown}
          theme={theme}
          coverage={coverage}
          animate={animate}
          shadows={shadows}
          onHover={onHover}
          onSelect={onSelect}
          onSettled={batchSettled}
        />
      ))}
      {hoverTarget && <HighlightOverlay target={hoverTarget} color={outlineColor} thickness={0.06} />}
      {selectTarget && <HighlightOverlay target={selectTarget} color={outlineColor} thickness={0.09} />}
    </group>
  )
}
