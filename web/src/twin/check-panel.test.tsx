import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { LabInfo } from '../builder/builder-api'
import { LAB } from '../builder/test-fixtures'
import { parseTwin, type TwinState } from '../graph/types'
import { THEMES } from '../scene/theme'
import { CheckPanel } from './check-panel'
import { useCheckSelection } from './use-check-selection'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const FIXTURES = resolve(import.meta.dirname, '../../../server/tests/fixtures/graph')
const TWIN = parseTwin(JSON.parse(readFileSync(`${FIXTURES}/lab-06-07.twin.json`, 'utf8')))
// The lab's task order, which the twin's checks do not follow.
const TASKS: LabInfo['tasks'] = ['vpc', 'subnets', 'internet-gateway', 'nat-gateway', 'routing'].map((id) => ({ id, text: `Task ${id}` }))
const WITH_PENDING: TwinState = {
  ...TWIN,
  checks: TWIN.checks.map((c) => (c.id === 'private-route-table' ? { ...c, status: 'pending', message: 'emulator không phản hồi' } : c)),
}

// The panel as the app uses it: the selection lives in useCheckSelection.
function Harness({ twin }: { twin: TwinState }) {
  const [selected, select] = useCheckSelection(twin)
  return <CheckPanel twin={twin} lab={{ ...LAB, tasks: TASKS }} selected={selected} onSelect={select} theme={THEMES.light} />
}

describe('CheckPanel', () => {
  let root: Root
  let host: HTMLElement
  const render = (twin: TwinState) => act(() => root.render(<Harness twin={twin} />))
  const item = (id: string) => host.querySelector<HTMLButtonElement>(`.check-item[data-check="${id}"]`)!
  const pressed = () => [...host.querySelectorAll('.check-item[aria-pressed="true"]')].map((b) => b.getAttribute('data-check'))

  beforeEach(() => {
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
  })

  it('groups the checks by task in the lab order', () => {
    render(TWIN)
    expect([...host.querySelectorAll('.check-task')].map((t) => t.getAttribute('data-task'))).toEqual(TASKS.map((t) => t.id))
    expect(host.querySelector('.check-task[data-task="routing"]')!.textContent).toContain('Task routing')
    expect(host.querySelector('#check-summary')!.textContent).toBe('4/8 đạt')
  })

  it('shows each of the three states with the latest message', () => {
    render(WITH_PENDING)
    const status = (id: string) => item(id).querySelector('.check-status')!.textContent
    expect(status('vpc-exists')).toBe('Đạt')
    expect(status('nat-in-public-subnet')).toBe('Chưa đạt')
    expect(status('private-route-table')).toBe('Đang chờ')
    expect(item('private-route-table').querySelector('.check-message')!.textContent).toBe('emulator không phản hồi')
    expect(item('private-route-table').dataset.status).toBe('pending')
  })

  it('selects a check on press and lets go on a second press or Esc', () => {
    render(TWIN)
    expect(pressed()).toEqual([])
    act(() => item('igw-attached').click())
    expect(pressed()).toEqual(['igw-attached'])
    act(() => item('vpc-exists').click())
    expect(pressed()).toEqual(['vpc-exists'])
    act(() => item('vpc-exists').click())
    expect(pressed()).toEqual([])
    act(() => item('vpc-exists').click())
    act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })))
    expect(pressed()).toEqual([])
  })

  it('lets go when the attempt changes', () => {
    render(TWIN)
    act(() => item('vpc-exists').click())
    render({ ...TWIN, attempt: TWIN.attempt! + 1 })
    expect(pressed()).toEqual([])
    render(TWIN) // the old attempt's selection does not come back
    expect(pressed()).toEqual([])
  })
})
