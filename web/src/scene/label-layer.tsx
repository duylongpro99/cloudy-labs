// Billboard labels above every leaf object, hidden as one group when zoomed out.
// Ghost labels are muted and say "mục tiêu"; an achieved object gets a tick above its label,
// an achieved badge (security group, Elastic IP) one right above itself.
import { Billboard, Text } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { memo, useRef } from 'react'
import type { Group } from 'three'
import { objectHeight, type AwsKind, type AwsObjectPlacement } from './aws-objects'
import type { LaidOutLeaf } from './layout'
import type { Theme } from './theme'
import { AchievedMark, FONT } from './tray-layer'

export const LABEL_MIN_ZOOM = 14 // node labels show only when zoomed in past this

// Memoised: re-rendering 200 Text labels on every hover change is the most expensive part of a scene update.
export const LabelLayer = memo(function LabelLayer({ leaves, badges = [], theme }: {
  leaves: LaidOutLeaf[]
  badges?: readonly AwsObjectPlacement[] // the achieved ones
  theme: Theme
}) {
  const labels = useRef<Group>(null)
  // Toggle one parent group instead of re-rendering every label on each zoom change.
  useFrame(({ camera }) => {
    if (labels.current) labels.current.visible = camera.zoom >= LABEL_MIN_ZOOM
  })
  return (
    <group ref={labels}>
      {leaves.map((l) => (
        <Billboard key={l.node.id} position={[l.x, l.y + objectHeight(l.node.kind as AwsKind) + 0.45, l.z]}>
          <Text
            font={FONT}
            fontSize={0.36}
            color={l.node.ghost ? theme.ghost.label : theme.label}
            outlineWidth={0.03}
            outlineColor={theme.labelOutline}
            anchorY="bottom"
          >
            {l.node.ghost ? `${l.node.label} · mục tiêu` : l.node.label}
          </Text>
          {l.node.achieved && <AchievedMark theme={theme} size={0.36} position={[0, 0.7, 0]} />}
        </Billboard>
      ))}
      {badges.map((b) => (
        <Billboard key={b.id} position={[b.position[0], b.position[1] + objectHeight(b.kind) + 0.25, b.position[2]]}>
          <AchievedMark theme={theme} size={0.28} />
        </Billboard>
      ))}
    </group>
  )
})
