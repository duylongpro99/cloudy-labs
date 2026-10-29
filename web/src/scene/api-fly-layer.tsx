// API calls "fly" from the upper left edge of the view to the node they touched (PRD F3.6).
// A write event waits for the next graph to pick its target (flyTarget); with no new graph within
// RESOLVE_MS it flies to the region tray. Frames are requested only while particles are in the air.
import { Billboard, Text } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { type Camera, type Group, Plane, QuadraticBezierCurve3, Raycaster, Vector2, Vector3 } from 'three'
import { flyLabel, flyTarget } from '../graph/fly-target'
import type { SceneGraph } from '../graph/graph-to-scene'
import type { ApiEvent } from '../graph/types'
import type { EdgeAnchor } from './object-placements'
import type { Theme } from './theme'
import { FONT } from './tray-layer'

export const FLY_MS = 600
export const MAX_FLYING = 8
const RESOLVE_MS = 1500
const LAUNCH_NDC = new Vector2(-0.95, 0.45) // left edge of the view, below the status panel in the top-left corner

interface Pending {
  event: ApiEvent
  before: SceneGraph
  beforeAnchors: Map<string, EdgeAnchor>
  timer: number
}

interface Particle {
  key: number
  label: string
  curve: QuadraticBezierCurve3
  start: number
}

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

// Where the top-left of the view meets the horizontal plane at `height`.
function launchPoint(camera: Camera, height: number) {
  const ray = new Raycaster()
  ray.setFromCamera(LAUNCH_NDC, camera)
  return ray.ray.intersectPlane(new Plane(new Vector3(0, 1, 0), -height), new Vector3()) ?? ray.ray.origin.clone()
}

export function ApiFlyLayer({
  events,
  scene,
  anchors,
  theme,
  countRef,
}: {
  events: readonly ApiEvent[]
  scene: SceneGraph
  anchors: Map<string, EdgeAnchor>
  theme: Theme
  countRef?: RefObject<number>
}) {
  const get = useThree((s) => s.get)
  const invalidate = useThree((s) => s.invalidate)
  const [particles, setParticles] = useState<Particle[]>([])
  const groups = useRef(new Map<number, Group>()).current
  const pending = useRef<Pending[]>([])
  // Events already on the list when the layer mounts happened before the learner could see them.
  const seen = useRef(new WeakSet(events)).current
  const latest = useRef({ scene, anchors })
  const nextKey = useRef(0)

  const launch = useCallback(
    (p: Pending, target: string | null) => {
      pending.current = pending.current.filter((q) => q !== p)
      clearTimeout(p.timer)
      const { scene, anchors } = latest.current
      const region = scene.nodes.find((n) => n.kind === 'region')
      // A removed target is no longer in the anchors, but it is still shrinking where it was.
      const to = (target && (anchors.get(target) ?? p.beforeAnchors.get(target))) || (region && anchors.get(region.id))
      if (!to) return
      const end = new Vector3(...to.at)
      const start = launchPoint(get().camera, end.y + 4)
      const mid = start.clone().lerp(end, 0.5)
      mid.y += 2 + start.distanceTo(end) * 0.1
      const particle = { key: nextKey.current++, label: flyLabel(p.event.action), curve: new QuadraticBezierCurve3(start, mid, end), start: performance.now() }
      setParticles((ps) => [...ps, particle].slice(-MAX_FLYING))
      invalidate()
    },
    [get, invalidate],
  )

  // Runs before the scene effect below, so an event that arrives in the same render as its graph
  // still records the previous scene as `before`.
  useEffect(() => {
    for (const event of events) {
      if (seen.has(event)) continue
      seen.add(event)
      if (!event.write) continue
      const p: Pending = { event, before: latest.current.scene, beforeAnchors: latest.current.anchors, timer: 0 }
      p.timer = window.setTimeout(() => launch(p, null), RESOLVE_MS)
      pending.current.push(p)
    }
  }, [events, seen, launch])

  useEffect(() => {
    latest.current = { scene, anchors }
    for (const p of pending.current) if (p.before !== scene) launch(p, flyTarget(p.event.action, p.before, scene))
  }, [scene, anchors, launch])

  useEffect(() => () => pending.current.forEach((p) => clearTimeout(p.timer)), [])
  useEffect(() => {
    if (countRef) countRef.current = particles.length
  }, [countRef, particles])

  useFrame(() => {
    if (particles.length === 0) return
    const now = performance.now()
    let landed = false
    for (const p of particles) {
      const t = (now - p.start) / FLY_MS
      if (t >= 1) landed = true
      const g = groups.get(p.key)
      if (g) p.curve.getPoint(easeInOut(Math.min(t, 1)), g.position)
    }
    if (landed) setParticles((ps) => ps.filter((p) => now - p.start < FLY_MS))
    invalidate()
  })

  return (
    <group>
      {particles.map((p) => (
        <group
          key={p.key}
          position={p.curve.v0}
          ref={(g) => {
            if (g) groups.set(p.key, g)
            else groups.delete(p.key)
          }}
        >
          <mesh>
            <sphereGeometry args={[0.3, 16, 12]} />
            <meshBasicMaterial color={theme.pulse} toneMapped={false} />
          </mesh>
          <Billboard position={[0, 0.45, 0]}>
            <Text font={FONT} fontSize={0.42} color={theme.label} outlineWidth={0.04} outlineColor={theme.labelOutline} anchorY="bottom">
              {p.label}
            </Text>
          </Billboard>
        </group>
      ))}
    </group>
  )
}
