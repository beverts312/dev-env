import type { ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'

export function renderApp(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

type Route = (init: RequestInit | undefined) => unknown

// stubs fetch: each "METHOD /path" answers its route's JSON; the calls are kept for asserting
export function mockApi(routes: Record<string, Route | object>) {
  const calls: { method: string; path: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    const path = url.pathname.replace(/^\/api/, '') + url.search
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const route = routes[`${method} ${path}`]
    if (route === undefined) return new Response(JSON.stringify({ message: `no route ${method} ${path}` }), { status: 404 })
    const data = typeof route === 'function' ? (route as Route)(init) : route
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}
