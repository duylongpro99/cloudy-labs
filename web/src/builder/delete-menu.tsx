// The menu a right-click on an object opens: its kind's delete ops. Choosing one opens the op's
// form, so the learner still sees the command before anything runs.
import { useEffect, useRef } from 'react'
import type { PanelAction } from '../scene/property-panel'
import type { Theme } from '../scene/theme'

export function DeleteMenu({ x, y, label, actions, theme, onClose }: {
  x: number
  y: number
  label: string // the object's name, for the menu's accessible name
  actions: readonly PanelAction[]
  theme: Theme
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const away = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('pointerdown', away, true)
    window.addEventListener('keydown', key)
    return () => {
      window.removeEventListener('pointerdown', away, true)
      window.removeEventListener('keydown', key)
    }
  }, [onClose])
  return (
    <div
      id="delete-menu"
      ref={ref}
      role="menu"
      aria-label={`Xoá ${label}`}
      style={{
        position: 'fixed',
        left: Math.min(x, window.innerWidth - 240),
        top: Math.min(y, window.innerHeight - 40 * (actions.length + 1)),
        minWidth: 200,
        padding: 4,
        borderRadius: 6,
        background: theme.background,
        color: theme.label,
        boxShadow: '0 2px 8px rgba(0,0,0,.3)',
        fontSize: 13,
        zIndex: 20,
      }}
    >
      {actions.map((a) => (
        <button
          key={a.id}
          id={a.id}
          role="menuitem"
          onClick={() => {
            onClose()
            a.run()
          }}
          style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 10px', border: 0, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer' }}
        >
          {a.label}
        </button>
      ))}
    </div>
  )
}
