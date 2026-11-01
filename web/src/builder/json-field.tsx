// A text area for a field the API takes as a structure, a list of structures or a map. The text
// goes to the server as typed; the note under it says early when it is not JSON yet.
import type { CSSProperties } from 'react'

export function jsonProblem(text: string): string | null {
  if (!text.trim()) return null
  try {
    JSON.parse(text)
    return null
  } catch (e) {
    return `Chưa phải JSON hợp lệ: ${e instanceof Error ? e.message : String(e)}`
  }
}

export function JsonField({ id, value, disabled, invalid, describedBy, style, onChange }: {
  id: string
  value: string
  disabled: boolean
  invalid: boolean
  describedBy?: string
  style: CSSProperties
  onChange: (value: string) => void
}) {
  const problem = jsonProblem(value)
  return (
    <>
      <textarea
        id={id}
        className="json-field"
        value={value}
        disabled={disabled}
        spellCheck={false}
        rows={Math.min(12, Math.max(3, value.split('\n').length))}
        placeholder="JSON"
        onChange={(e) => onChange(e.target.value)}
        style={{ ...style, fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
        aria-invalid={invalid || problem !== null}
        aria-describedby={[describedBy, problem ? `${id}-json` : undefined].filter(Boolean).join(' ') || undefined}
      />
      {problem && (
        <div id={`${id}-json`} className="json-problem" style={{ fontSize: 12, marginTop: 2, opacity: 0.85 }}>
          {problem}
        </div>
      )}
    </>
  )
}
