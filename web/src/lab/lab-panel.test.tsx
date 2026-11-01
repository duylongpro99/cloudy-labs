import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { LabTab } from '../builder/builder-api'
import { contentImageUrl, LabPanel } from './lab-panel'

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

// Written for the test; real course pages never enter the repo.
const TABS: LabTab[] = [
  { title: 'Giới thiệu', markdown: 'Một mạng nhỏ.\n\n<script>window.pwned = 1</script>\n\n<b onclick="x()">đậm?</b>' },
  {
    title: 'Mục tiêu',
    markdown: '| Bước | Việc |\n|---|---|\n| 1 | Tạo VPC |\n\n![sơ đồ](diagram.png) ![ngoài](https://cdn.example/x.png) [tài liệu](https://docs.aws.amazon.com/)',
  },
]

describe('LabPanel', () => {
  let root: Root
  let host: HTMLElement
  const render = (tabs: LabTab[]) => act(() => root.render(<LabPanel tabs={tabs} />))
  const body = () => host.querySelector('.lab-tab-body')!
  const tab = (title: string) => [...host.querySelectorAll<HTMLButtonElement>('.lab-tab')].find((b) => b.textContent === title)!

  beforeEach(() => {
    host = document.body.appendChild(document.createElement('div'))
    root = createRoot(host)
  })
  afterEach(() => {
    act(() => root.unmount())
    host.remove()
  })

  it('shows one tab per heading and switches between them', () => {
    render(TABS)
    expect([...host.querySelectorAll('.lab-tab')].map((b) => b.textContent)).toEqual(['Giới thiệu', 'Mục tiêu'])
    expect(tab('Giới thiệu').getAttribute('aria-selected')).toBe('true')
    act(() => tab('Mục tiêu').click())
    expect(tab('Mục tiêu').getAttribute('aria-selected')).toBe('true')
    expect(body().querySelectorAll('table td')).toHaveLength(2)
  })

  it('shows raw HTML as text and never puts it in the DOM', () => {
    render(TABS)
    expect(body().querySelector('script, b')).toBeNull()
    expect(body().textContent).toContain('<script>window.pwned = 1</script>')
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined()
  })

  it('loads images only from the lab content endpoint; others become links', () => {
    render(TABS)
    act(() => tab('Mục tiêu').click())
    expect([...body().querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/api/lab/content/diagram.png'])
    const external = body().querySelector<HTMLAnchorElement>('a.external-image')!
    expect(external.getAttribute('href')).toBe('https://cdn.example/x.png')
    expect([...body().querySelectorAll('a')].every((a) => a.rel === 'noopener noreferrer')).toBe(true)
  })

  it('renders nothing without tabs', () => {
    render([])
    expect(host.querySelector('#lab-panel')).toBeNull()
  })
})

describe('contentImageUrl', () => {
  it('accepts plain image names only', () => {
    expect(contentImageUrl('./a-1.PNG')).toBe('/api/lab/content/a-1.PNG')
    for (const bad of ['../x.png', 'a/b.png', 'x.html', 'https://h/x.png', 'javascript:alert(1)', undefined, '']) {
      expect(contentImageUrl(bad)).toBeNull()
    }
  })
})
