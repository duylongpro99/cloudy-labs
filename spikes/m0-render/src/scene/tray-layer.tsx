// Nested translucent trays for Region / VPC / AZ / Subnet with AWS group border colours.
import { Line, Text } from '@react-three/drei'
import type { LaidOutGroup } from './layout'
import { TRAY_H } from './layout'
import type { Theme } from './theme'

const FONT = '/fonts/BeVietnamPro-Medium.woff'

function Tray({ g, theme }: { g: LaidOutGroup; theme: Theme }) {
  const style = theme.groups[g.kind]
  const top = g.y + TRAY_H + 0.01
  const corners: [number, number, number][] = [
    [g.x, top, g.z],
    [g.x + g.w, top, g.z],
    [g.x + g.w, top, g.z + g.d],
    [g.x, top, g.z + g.d],
    [g.x, top, g.z],
  ]
  // Line2 has no dash-dot pattern; a long dash with a short gap stands in for it.
  const dash = style.dashed === 'dash' ? { dashSize: 0.5, gapSize: 0.35 } : { dashSize: 1.4, gapSize: 0.3 }
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
        position={[g.x + 0.9, top + 0.005, g.z + g.d - 0.6]}
        renderOrder={g.level + 0.6}
      >
        {g.node.label}
      </Text>
    </group>
  )
}

export function TrayLayer({ groups, theme }: { groups: LaidOutGroup[]; theme: Theme }) {
  return (
    <group>
      {groups.map((g) => (
        <Tray key={g.node.id} g={g} theme={theme} />
      ))}
    </group>
  )
}
