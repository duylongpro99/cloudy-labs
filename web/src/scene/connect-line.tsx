// Drawing an edge between two objects (PRD F4.6): a handle above the selected object that can
// start one, and the temporary line from it to the pointer while the learner drags.
import { Line } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import type { Vec3 } from '../builder/drop-targets'
import type { Theme } from './theme'

export const HANDLE_RISE = 0.9 // above the object's top face

export function ConnectHandle({ at, theme, onHover, onStart }: { at: Vec3; theme: Theme; onHover: (over: boolean) => void; onStart: () => void }) {
  return (
    <mesh
      position={[at[0], at[1] + HANDLE_RISE, at[2]]}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation()
        onHover(true)
      }}
      onPointerOut={() => onHover(false)}
      onPointerDown={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation()
        onStart()
      }}
    >
      <sphereGeometry args={[0.32, 24, 16]} />
      <meshBasicMaterial color={theme.outline} toneMapped={false} />
    </mesh>
  )
}

export function ConnectLine({ from, to, valid, theme }: { from: Vec3; to: Vec3; valid: boolean; theme: Theme }) {
  return (
    <Line
      points={[[from[0], from[1] + HANDLE_RISE, from[2]], [to[0], to[1] + 0.05, to[2]]]}
      color={valid ? theme.outline : theme.edge}
      lineWidth={3}
      dashed={!valid}
      dashSize={0.4}
      gapSize={0.3}
      depthTest={false}
      renderOrder={20}
    />
  )
}
