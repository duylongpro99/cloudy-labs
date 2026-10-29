// During a drag, tints every tray that can take the dragged resource in the theme's outline
// colour (stronger under the pointer) and dims the trays that cannot. Drawn as thin planes just
// above the trays, so TrayLayer's own fades stay untouched.
import type { Theme } from './theme'
import { TRAY_H, type LaidOutGroup } from './layout'

export function DropHighlight({ groups, accepts, target, theme }: { groups: readonly LaidOutGroup[]; accepts: (g: LaidOutGroup) => boolean; target: string | null; theme: Theme }) {
  return (
    <group>
      {groups.map((g) => {
        const ok = accepts(g)
        const opacity = g.node.id === target ? 0.45 : ok ? 0.16 : 0.5
        return (
          <mesh key={g.node.id} position={[g.x + g.w / 2, g.y + TRAY_H + 0.02, g.z + g.d / 2]} rotation-x={-Math.PI / 2} renderOrder={g.level + 0.7}>
            <planeGeometry args={[g.w, g.d]} />
            <meshBasicMaterial color={ok ? theme.outline : theme.background} transparent opacity={opacity} depthWrite={false} toneMapped={false} />
          </mesh>
        )
      })}
    </group>
  )
}
