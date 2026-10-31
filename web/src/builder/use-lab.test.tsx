import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchLab } from './builder-api'
import { LAB } from './test-fixtures'
import { useLab } from './use-lab'

vi.mock('./builder-api', () => ({ fetchLab: vi.fn() }))

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function Probe({ changed }: { changed: string | null }) {
  const { lab } = useLab(changed)
  return <span id="attempt">{lab?.attempt ?? ''}</span>
}

describe('useLab', () => {
  let root: Root
  let host: HTMLElement
  const render = (changed: string | null) => act(async () => root.render(<Probe changed={changed} />))
  const attempt = () => host.querySelector('#attempt')!.textContent

  beforeEach(() => {
    vi.mocked(fetchLab).mockReset()
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
  })

  it('fetches the lab again when the twin moves to a new attempt, without waiting for focus', async () => {
    vi.mocked(fetchLab).mockResolvedValueOnce({ ...LAB, attempt: 1 }).mockResolvedValueOnce({ ...LAB, attempt: 2 })
    await render('fixture-lab-06#1')
    expect(attempt()).toBe('1')
    await render('fixture-lab-06#1')
    expect(fetchLab).toHaveBeenCalledTimes(1)
    await render('fixture-lab-06#2')
    expect(fetchLab).toHaveBeenCalledTimes(2)
    expect(attempt()).toBe('2')
  })
})
