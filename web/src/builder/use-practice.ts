// Practice mode (F4.7), shared by the builder and the chat: one switch for the whole page,
// remembered per browser. Storage may be missing or throw (private windows, blocked site data):
// once a write fails, the page's own copy is the switch.
import { useSyncExternalStore } from 'react'

const PRACTICE_KEY = 'cloudy-labs:practice'
const listeners = new Set<() => void>()
let pageCopy: boolean | null = null // set when storage would not take the last change

function read(): boolean {
  if (pageCopy !== null) return pageCopy
  try {
    return localStorage.getItem(PRACTICE_KEY) === '1'
  } catch {
    return false
  }
}

export function setPractice(on: boolean) {
  try {
    localStorage.setItem(PRACTICE_KEY, on ? '1' : '0')
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

export function usePractice(): [boolean, (on: boolean) => void] {
  return [useSyncExternalStore(subscribe, read), setPractice]
}
