// Billboard labels above every leaf object, hidden as one group when zoomed out.
import { Billboard, Text } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { memo, useRef } from 'react'
import type { Group } from 'three'
import { objectHeight, type AwsKind } from './aws-objects'
import type { LaidOutLeaf } from './layout'
import type { Theme } from './theme'
import { FONT } from './tray-layer'

export const LABEL_MIN_ZOOM = 14 // node labels show only when zoomed in past this

// Memoised: re-rendering 200 Text labels on every hover change is the most expensive part of a scene update.
export const LabelLayer = memo(function LabelLayer({ leaves, theme }: { leaves: LaidOutLeaf[]; theme: Theme }) {
  const labels = useRef<Group>(null)
  // Toggle one parent group instead of re-rendering every label on each zoom change.
  useFrame(({ camera }) => {
    if (labels.current) labels.current.visible = camera.zoom >= LABEL_MIN_ZOOM
  })
  return (
    <group ref={labels}>
      {leaves.map((l) => (
        <Billboard key={l.node.id} position={[l.x, l.y + objectHeight(l.node.kind as AwsKind) + 0.45, l.z]}>
          <Text font={FONT} fontSize={0.36} color={theme.label} outlineWidth={0.03} outlineColor={theme.labelOutline} anchorY="bottom">
            {l.node.label}
          </Text>
        </Billboard>
      ))}
    </group>
  )
})
