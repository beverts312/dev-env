import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { clearPersistent } from '@/lib/store'

// what Radix and the sidebar ask of the browser, which jsdom lacks
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    onchange: null,
    dispatchEvent: () => false,
  }) as MediaQueryList
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false

afterEach(() => {
  cleanup()
  clearPersistent()
  vi.restoreAllMocks()
})
