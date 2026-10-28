import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { MANIFEST, MANIFEST_BY_KIND, REQUIRED_KINDS } from './manifest'

const iconDir = resolve(import.meta.dirname, 'icons')

describe('icon manifest', () => {
  it('has exactly one entry per required kind', () => {
    expect(MANIFEST.map((e) => e.kind).sort()).toEqual([...REQUIRED_KINDS].sort())
  })

  it('gives every kind except outline-only an icon file present in icons/', () => {
    for (const kind of REQUIRED_KINDS) {
      const e = MANIFEST_BY_KIND[kind]
      if (e.role === 'outline-only') {
        expect(e.file, kind).toBeUndefined()
        continue
      }
      expect(e.file, kind).toBeTruthy()
      expect(existsSync(resolve(iconDir, e.file!)), `${kind}: ${e.file}`).toBe(true)
    }
  })

  it('names copied files after their source in the AWS package', () => {
    for (const e of MANIFEST.filter((e) => e.source)) expect(e.source!.endsWith(`/${e.file}`), e.kind).toBe(true)
  })

  it('lists every AWS-sourced file in NOTICE.md', () => {
    const notice = readFileSync(resolve(iconDir, 'NOTICE.md'), 'utf8')
    for (const e of MANIFEST.filter((e) => e.file)) expect(notice, e.kind).toContain(e.file!)
  })
})
