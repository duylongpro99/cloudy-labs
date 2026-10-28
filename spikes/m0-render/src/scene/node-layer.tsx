// Service blocks: icon on top, billboard label hidden when zoomed out,
// react-spring entrance, Outlines on hover or selection.
import { animated, useSpring } from '@react-spring/three'
import { Billboard, Outlines, Text } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef, useState } from 'react'
import type { Group } from 'three'
import type { LeafKind } from '../fixture'
import { iconTexture } from './icons'
import type { LaidOutLeaf } from './layout'
import { BLOCK } from './layout'
import type { Theme, ThemeName } from './theme'

const FONT = '/fonts/BeVietnamPro-Medium.woff'
const HEIGHT: Record<LeafKind, number> = { instance: 0.9, nat: 0.6, igw: 0.6 }
export const LABEL_MIN_ZOOM = 14 // node labels show only when zoomed in past this

function Block({ leaf, index, theme, themeName, selected, onSelect }: {
  leaf: LaidOutLeaf
  index: number
  theme: Theme
  themeName: ThemeName
  selected: boolean
  onSelect: (id: string) => void
}) {
  const kind = leaf.node.kind as LeafKind
  const h = HEIGHT[kind]
  const [hovered, setHovered] = useState(false)
  const invalidate = useThree((s) => s.invalidate)
  const icon = useMemo(() => iconTexture(kind, themeName, invalidate), [kind, themeName, invalidate])
  const { scale } = useSpring({ from: { scale: 0.001 }, to: { scale: 1 }, delay: index * 4, config: { tension: 220, friction: 22 } })
  return (
    <animated.group position={[leaf.x, leaf.y, leaf.z]} scale={scale}>
      <mesh
        position={[0, h / 2, 0]}
        castShadow
        receiveShadow
        onPointerOver={(e) => (e.stopPropagation(), setHovered(true))}
        onPointerOut={() => setHovered(false)}
        onClick={(e) => (e.stopPropagation(), onSelect(leaf.node.id))}
      >
        <boxGeometry args={[BLOCK, h, BLOCK]} />
        <meshStandardMaterial color={theme.block[kind]} roughness={0.75} metalness={0} />
        {/* World-unit thickness: screenspace Outlines blew up into a large artifact under the ortho camera. */}
        {(hovered || selected) && <Outlines thickness={selected ? 0.09 : 0.06} color={theme.outline} />}
      </mesh>
      <mesh position={[0, h + 0.002, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[BLOCK * 0.8, BLOCK * 0.8]} />
        <meshBasicMaterial map={icon} transparent toneMapped={false} />
      </mesh>
    </animated.group>
  )
}

export function NodeLayer({ leaves, theme, themeName, selected, onSelect }: {
  leaves: LaidOutLeaf[]
  theme: Theme
  themeName: ThemeName
  selected: string | null
  onSelect: (id: string) => void
}) {
  const labels = useRef<Group>(null)
  // Toggle one parent group instead of re-rendering 179 labels on every zoom change.
  useFrame(({ camera }) => {
    if (labels.current) labels.current.visible = camera.zoom >= LABEL_MIN_ZOOM
  })
  return (
    <group>
      {leaves.map((l, i) => (
        <Block key={l.node.id} leaf={l} index={i} theme={theme} themeName={themeName} selected={selected === l.node.id} onSelect={onSelect} />
      ))}
      <group ref={labels}>
        {leaves.map((l) => (
          <Billboard key={l.node.id} position={[l.x, l.y + HEIGHT[l.node.kind as LeafKind] + 0.55, l.z]}>
            <Text font={FONT} fontSize={0.36} color={theme.label} outlineWidth={0.03} outlineColor={theme.labelOutline} anchorY="bottom">
              {l.node.label}
            </Text>
          </Billboard>
        ))}
      </group>
    </group>
  )
}
