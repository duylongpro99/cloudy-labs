// Whether the scene shows the lab's target as ghosts (PRD F6.2): on unless the learner turned it
// off, remembered per browser. Storage may be missing or throw (private windows, blocked site
// data): once a write fails, the page's own copy is the switch.
import { useSyncExternalStore } from 'react'

const GHOST_KEY = 'cloudy-labs:ghost'
const listeners = new Set<() => void>()
let pageCopy: boolean | null = null // set when storage would not take the last change

function read(): boolean {
  if (pageCopy !== null) return pageCopy
  try {
    return localStorage.getItem(GHOST_KEY) !== '0'
  } catch {
    return true
  }
}

export function setShowGhosts(on: boolean) {
  try {
    localStorage.setItem(GHOST_KEY, on ? '1' : '0')
    pageCopy = null
  } catch {
    pageCopy = on
  }
  listeners.forEach((l) => l())
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useGhostToggle(): [boolean, (on: boolean) => void] {
  return [useSyncExternalStore(subscribe, read), setShowGhosts]
}
