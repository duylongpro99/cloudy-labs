// While the learner drags something from the palette or draws an edge, reports what lies under
// the pointer: the trays its ray crosses (deepest first) and where it meets the scene. Listens on
// the window, so a drag that starts in the HTML palette is followed into the canvas; the pointer
// counts only while the canvas itself is under it (the drag ghost has pointer-events: none).
import { useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import { Raycaster, Vector2 } from 'three'
import { traysUnder, type Vec3 } from '../builder/drop-targets'
import { TRAY_H, type LaidOutGroup } from './layout'

export interface ScenePointer {
  inCanvas: boolean
  trays: LaidOutGroup[]
  point: Vec3 | null // on the top face of the deepest tray, or the ground
}

export function PointerProbe({ groups, onMove, onEnd }: { groups: readonly LaidOutGroup[]; onMove: (p: ScenePointer) => void; onEnd: (p: ScenePointer) => void }) {
  const camera = useThree((s) => s.camera)
  const gl = useThree((s) => s.gl)
  useEffect(() => {
    const ray = new Raycaster()
    const ndc = new Vector2()
    const read = (e: PointerEvent): ScenePointer => {
      if (e.target !== gl.domElement) return { inCanvas: false, trays: [], point: null }
      const r = gl.domElement.getBoundingClientRect()
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      ray.setFromCamera(ndc, camera)
      const { origin: o, direction: d } = ray.ray
      const trays = traysUnder(groups, [o.x, o.y, o.z], [d.x, d.y, d.z])
      const y = trays[0] ? trays[0].y + TRAY_H : 0
      const t = (y - o.y) / d.y
      return { inCanvas: true, trays, point: d.y ? [o.x + t * d.x, y, o.z + t * d.z] : null }
    }
    const move = (e: PointerEvent) => onMove(read(e))
    const up = (e: PointerEvent) => onEnd(read(e))
    // The browser took the pointer away (touch gesture, tab switch): end the drag where nothing can land.
    const cancel = () => onEnd({ inCanvas: false, trays: [], point: null })
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [groups, camera, gl, onMove, onEnd])
  return null
}
