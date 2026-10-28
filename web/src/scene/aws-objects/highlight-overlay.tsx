// Outline for one hovered or selected object. Instances cannot carry their own Outlines,
// so an invisible copy of the plinth is placed on top of the instance and outlined instead.
// Thickness is in world units: screenspace Outlines broke up under the orthographic camera.
import { Outlines } from '@react-three/drei'
import type { AwsObjectPlacement } from './aws-object-layer'
import { outlineGeometry } from './geometry-cache'

const noRaycast = () => {}

export function HighlightOverlay({ target, color, thickness }: { target: AwsObjectPlacement; color: string; thickness: number }) {
  return (
    <mesh geometry={outlineGeometry(target.kind)} position={target.position} raycast={noRaycast} userData={{ highlight: target.id }}>
      <meshBasicMaterial colorWrite={false} depthWrite={false} />
      <Outlines thickness={thickness} color={color} angle={0} />
    </mesh>
  )
}
