// The lab's palette (PRD F4.1): only the kinds the lab lists, with the object library's icons.
// A drag starts on pointerdown and is followed by the scene's pointer probe; HTML5 drag-and-drop
// is not used because the canvas cannot ray-cast during `dragover`.
import { useEffect, useState } from 'react'
import { MANIFEST_BY_KIND, type AwsKind } from '../scene/aws-objects'
import type { Theme } from '../scene/theme'
import { createOpFor, kindLabel } from './drop-targets'
import type { LabInfo } from './builder-api'

const ICON_URL = import.meta.glob('../scene/aws-objects/icons/*.svg', { query: '?url', import: 'default', eager: true }) as Record<string, string>

// The palette's "subnet" becomes public or private by its route table, so it borrows the public icon.
const ICON_KIND: Record<string, AwsKind> = { subnet: 'subnet-public' }

export function iconUrl(kind: string): string | undefined {
  const file = MANIFEST_BY_KIND[(ICON_KIND[kind] ?? kind) as AwsKind]?.file
  return file && ICON_URL[`../scene/aws-objects/icons/${file}`]
}

export function Palette({ lab, disabled, onStart }: { lab: LabInfo; disabled: boolean; onStart: (kind: string) => void }) {
  const kinds = lab.palette.filter((k) => createOpFor(lab.ops, k))
  return (
    <div id="palette" role="toolbar" aria-label="Tài nguyên kéo vào cảnh" style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {kinds.map((kind) => (
        <button
          key={kind}
          data-kind={kind}
          disabled={disabled}
          title={`Kéo ${kindLabel(kind)} vào cảnh`}
          onPointerDown={(e) => {
            if (e.button !== 0 || disabled) return
            e.preventDefault() // no text selection while dragging
            onStart(kind)
          }}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', cursor: 'grab', touchAction: 'none' }}
        >
          {iconUrl(kind) && <img src={iconUrl(kind)} alt="" width={20} height={20} draggable={false} />}
          {kindLabel(kind)}
        </button>
      ))}
    </div>
  )
}

// Follows the pointer during a drag or an edge drag: the resource's icon and what a drop would do.
export function DragGhost({ kind, hint, ok, theme }: { kind: string | null; hint: string; ok: boolean; theme: Theme }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  useEffect(() => {
    const move = (e: PointerEvent) => setAt({ x: e.clientX, y: e.clientY })
    window.addEventListener('pointermove', move)
    return () => window.removeEventListener('pointermove', move)
  }, [])
  if (!at) return null
  return (
    <div
      id="drag-ghost"
      data-ok={ok}
      style={{
        position: 'fixed',
        left: at.x + 14,
        top: at.y + 14,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        maxWidth: 360,
        padding: '4px 8px',
        borderRadius: 6,
        background: theme.background,
        color: theme.label,
        border: `1px solid ${ok ? theme.outline : theme.edge}`,
        boxShadow: '0 1px 4px rgba(0,0,0,.25)',
        fontSize: 12,
        zIndex: 10,
      }}
    >
      {kind && iconUrl(kind) && <img src={iconUrl(kind)} alt="" width={24} height={24} />}
      <span>{hint}</span>
    </div>
  )
}
