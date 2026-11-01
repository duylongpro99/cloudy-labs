// The lab's theory, one tab per level-2 heading of the learner's local `content/lab.md`.
// Markdown only: raw HTML shows as text, images load only from the lab-server's content endpoint,
// and an image from anywhere else is shown as a link the learner can choose to open.
import { useState } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { LabTab } from '../builder/builder-api'

const IMAGE_NAME = /^[A-Za-z0-9._-]{1,100}\.(png|jpg|jpeg|gif|webp|svg)$/i

// The address the page may load an image from, or null for anything outside the lab's content.
export function contentImageUrl(src: string | undefined): string | null {
  const name = src?.replace(/^\.\//, '')
  return name && IMAGE_NAME.test(name) ? `/api/lab/content/${encodeURIComponent(name)}` : null
}

const COMPONENTS: Components = {
  img({ src, alt }) {
    const url = contentImageUrl(typeof src === 'string' ? src : undefined)
    if (url) return <img src={url} alt={alt ?? ''} style={{ maxWidth: '100%' }} />
    return (
      <a href={typeof src === 'string' ? src : undefined} target="_blank" rel="noopener noreferrer" className="external-image">
        [ảnh{alt ? `: ${alt}` : ''}]
      </a>
    )
  },
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    )
  },
  table({ children }) {
    return <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>{children}</table>
  },
  th({ children }) {
    return <th style={{ border: '1px solid rgba(127,127,127,.4)', padding: '2px 6px', textAlign: 'left' }}>{children}</th>
  },
  td({ children }) {
    return <td style={{ border: '1px solid rgba(127,127,127,.4)', padding: '2px 6px' }}>{children}</td>
  },
  pre({ children }) {
    return <pre style={{ padding: 8, borderRadius: 6, background: 'rgba(127,127,127,.12)', overflow: 'auto', fontSize: 12 }}>{children}</pre>
  },
}

interface MdNode {
  type: string
  children?: MdNode[]
}

// Raw HTML in a pasted page is shown as the text it is, never parsed into the DOM.
function htmlAsText() {
  const walk = (node: MdNode) => {
    if (node.type === 'html') node.type = 'text'
    node.children?.forEach(walk)
  }
  return walk
}

export function LabMarkdown({ markdown }: { markdown: string }) {
  return (
    <Markdown remarkPlugins={[remarkGfm, htmlAsText]} components={COMPONENTS}>
      {markdown}
    </Markdown>
  )
}

export function LabPanel({ tabs }: { tabs: LabTab[] }) {
  const [active, setActive] = useState(0)
  if (tabs.length === 0) return null
  const tab = tabs[Math.min(active, tabs.length - 1)]
  return (
    // Folded by default: the theory is long and the scene matters more while building.
    <details id="lab-panel" aria-label="Bài lab" style={{ marginTop: 8 }}>
      <summary style={{ cursor: 'pointer' }}>
        <b>Bài lab</b> · {tabs.length} mục
      </summary>
      <div role="tablist" style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
        {tabs.map((t, i) => (
          <button key={`${i}:${t.title}`} role="tab" className="lab-tab" aria-selected={t === tab} onClick={() => setActive(i)}>
            {t.title}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="lab-tab-body" style={{ maxHeight: '50vh', overflow: 'auto', marginTop: 6, fontSize: 13 }}>
        <LabMarkdown markdown={tab.markdown} />
      </div>
    </details>
  )
}
