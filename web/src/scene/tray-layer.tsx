// Nested translucent trays for Region / VPC / AZ / Subnet with AWS group border colours.
// Groups with a tray badge get their label moved right to sit beside the badge.
import { Line, Text } from '@react-three/drei'
import { memo, useMemo } from 'react'
import { MANIFEST_BY_KIND, TRAY_LABEL_FROM_NEAR_EDGE, TRAY_LABEL_INSET, TRAY_LABEL_SHIFT } from './aws-objects'
import type { LaidOutGroup } from './layout'
import { TRAY_H } from './layout'
import type { Theme } from './theme'

export const FONT = '/fonts/BeVietnamPro-Medium.woff'

function Tray({ g, theme }: { g: LaidOutGroup; theme: Theme }) {
  const style = theme.groups[g.kind]
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
  const labelX = g.x + TRAY_LABEL_INSET + (MANIFEST_BY_KIND[g.kind].role === 'tray-badge' ? TRAY_LABEL_SHIFT : 0)
  return (
    <group>
      <mesh
        position={[g.x + g.w / 2, g.y + TRAY_H / 2, g.z + g.d / 2]}
        renderOrder={g.level}
        receiveShadow
        // N8AO would otherwise skip transparent trays and leave blocks floating.
        userData={{ treatAsOpaque: true }}
      >
        <boxGeometry args={[g.w, TRAY_H, g.d]} />
        <meshStandardMaterial color={style.fill} transparent opacity={style.opacity} depthWrite={false} roughness={0.9} metalness={0} />
      </mesh>
      <Line
        points={corners}
        color={style.border}
        lineWidth={g.kind === 'region' || g.kind === 'vpc' ? 2.4 : 1.8}
        dashed={style.dashed !== 'none'}
        {...(style.dashed !== 'none' ? dash : {})}
        renderOrder={g.level + 0.5}
      />
      <Text
        font={FONT}
        fontSize={g.kind === 'region' || g.kind === 'vpc' ? 0.75 : 0.55}
        color={theme.label}
        outlineWidth={0.04}
        outlineColor={theme.labelOutline}
        anchorX="left"
        anchorY="middle"
        rotation={[-Math.PI / 2, 0, 0]}
        position={[labelX, top + 0.005, g.z + g.d - TRAY_LABEL_FROM_NEAR_EDGE]}
        renderOrder={g.level + 0.6}
      >
        {g.node.label}
      </Text>
    </group>
  )
}

// Memoised so hover and selection changes in the scene do not re-render every tray.
export const TrayLayer = memo(function TrayLayer({ groups, theme }: { groups: LaidOutGroup[]; theme: Theme }) {
  return (
    <group>
      {groups.map((g) => (
        <Tray key={g.node.id} g={g} theme={theme} />
      ))}
    </group>
  )
})
