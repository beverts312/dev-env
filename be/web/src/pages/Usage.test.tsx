import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ClaudeUsage, CursorUsage } from '@/lib/api'
import { Usage } from '@/pages/Usage'
import { mockApi, renderApp } from '@/test/render'

const USAGE: ClaudeUsage = {
  limits: [
    { label: 'Current session', percent: 9, resets: 'Oct 28 at 9:39pm (America/Denver)' },
    { label: 'Current week (all models)', percent: 92, resets: 'Oct 30 at 10:59am (America/Denver)' },
  ],
  plan_note: 'You are currently using your subscription to power your Claude Code usage',
  details: "What's contributing to your limits usage?",
  raw: '',
  error: null,
  fetched_at: 1_761_700_000,
}

const CURSOR: CursorUsage = {
  plan: 'Team',
  limits: [
    { label: 'Included', percent: 12, resets: 'Nov 13' },
    { label: 'Auto', percent: 11, resets: 'Nov 13' },
    { label: 'API', percent: 16, resets: 'Nov 13' },
  ],
  on_demand: { kind: 'fixed', used_dollars: 12.34, limit_dollars: 50 },
  message: '',
  error: null,
  fetched_at: 1_761_700_000,
}

describe('Usage', () => {
  it('shows each limit as a bar with when it resets', async () => {
    mockApi({ 'GET /claude-usage': USAGE, 'GET /cursor-usage': CURSOR })
    renderApp(<Usage />)
    const week = await screen.findByRole('progressbar', { name: 'Current week (all models)' })
    expect(week).toHaveAttribute('aria-valuenow', '92')
    expect(screen.getByRole('progressbar', { name: 'Current session' })).toHaveAttribute('aria-valuenow', '9')
    expect(screen.getByText('resets Oct 30 at 10:59am (America/Denver)')).toBeInTheDocument()
    expect(screen.getByText("What's contributing to your limits usage?")).toBeInTheDocument()
  })

  it('says why usage could not be read', async () => {
    mockApi({ 'GET /cursor-usage': CURSOR, 'GET /claude-usage': { ...USAGE, limits: [], error: 'claude is not installed or not on PATH' } })
    renderApp(<Usage />)
    expect(await screen.findByText('claude is not installed or not on PATH')).toBeInTheDocument()
  })

  it('shows what /usage said when it has no limits', async () => {
    mockApi({ 'GET /cursor-usage': CURSOR, 'GET /claude-usage': { ...USAGE, limits: [], plan_note: '', raw: 'You are using an API key' } })
    renderApp(<Usage />)
    expect(await screen.findByText('You are using an API key')).toBeInTheDocument()
  })

  it('shows Cursor usage and on-demand spend', async () => {
    mockApi({ 'GET /claude-usage': USAGE, 'GET /cursor-usage': CURSOR })
    renderApp(<Usage />)
    const cursor = await screen.findByRole('region', { name: 'Cursor' })
    expect(await within(cursor).findByRole('progressbar', { name: 'API' })).toHaveAttribute('aria-valuenow', '16')
    expect(within(cursor).getByText('Team plan')).toBeInTheDocument()
    expect(within(cursor).getByText('$12.34 of $50.00 on-demand')).toBeInTheDocument()
  })

  it('shows a Cursor error without hiding Claude', async () => {
    mockApi({ 'GET /claude-usage': USAGE, 'GET /cursor-usage': { ...CURSOR, limits: [], on_demand: null, error: 'Cursor login expired' } })
    renderApp(<Usage />)
    expect(await screen.findByText('Cursor login expired')).toBeInTheDocument()
    expect(await screen.findByRole('progressbar', { name: 'Current session' })).toBeInTheDocument()
  })

  it('says when on-demand usage is off', async () => {
    mockApi({ 'GET /claude-usage': USAGE, 'GET /cursor-usage': { ...CURSOR, on_demand: { kind: 'disabled', used_dollars: 0, limit_dollars: null } } })
    renderApp(<Usage />)
    expect(await screen.findByText('on-demand usage is off')).toBeInTheDocument()
  })
})
