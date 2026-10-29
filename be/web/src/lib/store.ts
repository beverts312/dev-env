import { useCallback, useSyncExternalStore } from 'react'

// Settings the browser remembers (filters, collapsed tables, the review agent), kept in
// localStorage as JSON and shared live between every component reading the same key.
// Storage can be missing or throw (private windows, blocked site data), so the app works without it.

const listeners = new Map<string, Set<() => void>>()
// the parsed value for each key's raw string, so a snapshot only changes when the value does
const cache = new Map<string, { raw: string | null; value: unknown }>()
// values set while storage is unavailable
const memory = new Map<string, string>()

function readRaw(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return memory.get(key) ?? null
  }
}

function writeRaw(key: string, raw: string) {
  try {
    localStorage.setItem(key, raw)
  } catch {
    memory.set(key, raw)
  }
}

export function readPersistent<T>(key: string, fallback: T): T {
  const raw = readRaw(key)
  const hit = cache.get(key)
  if (hit && hit.raw === raw) return hit.value as T
  let value: unknown = fallback
  if (raw !== null) {
    try {
      value = JSON.parse(raw)
    } catch {
      // a value saved by an older page, or by hand
    }
  }
  cache.set(key, { raw, value })
  return value as T
}

export function writePersistent<T>(key: string, value: T) {
  writeRaw(key, JSON.stringify(value))
  listeners.get(key)?.forEach((notify) => notify())
}

function subscribe(key: string, notify: () => void) {
  let set = listeners.get(key)
  if (!set) listeners.set(key, (set = new Set()))
  set.add(notify)
  return () => set.delete(notify)
}

export function usePersistent<T>(key: string, fallback: T): [T, (next: T | ((prev: T) => T)) => void] {
  const value = useSyncExternalStore(
    useCallback((notify) => subscribe(key, notify), [key]),
    () => readPersistent(key, fallback),
  )
  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const prev = readPersistent(key, fallback)
      writePersistent(key, typeof next === 'function' ? (next as (prev: T) => T)(prev) : next)
    },
    // fallback is only read when nothing is stored, so a new one each render is fine
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  )
  return [value, set]
}

// for tests
export function clearPersistent() {
  cache.clear()
  memory.clear()
  try {
    localStorage.clear()
  } catch {
    // nothing to clear
  }
}
