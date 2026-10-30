import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { SkillPage as Page } from '@/lib/api'
import { SkillPage } from '@/pages/SkillPage'
import { mockApi, renderApp } from '@/test/render'

const PAGE: Page = {
  name: 'finops',
  skill: 'gcp-spend',
  icon: 'circle-dollar-sign',
  output: '~/reports/*.html',
  cwd: '/home/me/.be/pages/finops',
  file: '/home/me/reports/a.html',
  updated_at: 1_761_700_000,
  running: false,
  started_at: null,
  exit_code: null,
  error: null,
  links: [],
}

function renderPage() {
  return renderApp(
    <Routes>
      <Route path="p/:name" element={<SkillPage />} />
    </Routes>,
    '/p/finops',
  )
}

describe('SkillPage', () => {
  it('shows the newest output in a sandboxed frame', async () => {
    mockApi({ 'GET /pages/finops': PAGE })
    renderPage()
    const frame = await screen.findByTitle('finops')
    expect(frame).toHaveAttribute('src', '/api/pages/finops/content?v=1761700000')
    expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-popups')
  })

  it('says there is no output yet', async () => {
    mockApi({ 'GET /pages/finops': { ...PAGE, file: null, updated_at: null } })
    renderPage()
    expect(await screen.findByText(/refresh to run \/gcp-spend/)).toBeInTheDocument()
    expect(screen.queryByTitle('finops')).not.toBeInTheDocument()
  })

  it('refreshes, then shows it running', async () => {
    let running = false
    const calls = mockApi({
      'GET /pages/finops': () => ({ ...PAGE, running, started_at: running ? 1_761_700_100 : null }),
      'POST /pages/finops/refresh': () => {
        running = true
        return { message: 'refreshing finops with /gcp-spend' }
      },
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'refresh' }))
    expect(await screen.findByRole('button', { name: 'refreshing' })).toBeDisabled()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/pages/finops/refresh')).toBe(true)
    expect(await screen.findByText(/refreshing since/)).toBeInTheDocument()
  })

  it('links the artifacts the last run published', async () => {
    const links = ['https://claude.ai/artifact/abc', 'https://claude.ai/code/artifact/def']
    mockApi({ 'GET /pages/finops': { ...PAGE, links } })
    renderPage()
    const first = await screen.findByRole('link', { name: 'artifact 1' })
    expect(first).toHaveAttribute('href', links[0])
    expect(first).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('link', { name: 'artifact 2' })).toHaveAttribute('href', links[1])
  })

  it('shows why the last run failed', async () => {
    mockApi({ 'GET /pages/finops': { ...PAGE, exit_code: 1, error: 'claude exited 1\nno access' } })
    renderPage()
    expect(await screen.findByText(/no access/)).toBeInTheDocument()
  })
})
