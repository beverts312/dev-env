import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AgentPicker } from '@/components/AgentPicker'
import { mockApi, renderApp } from '@/test/render'

const CLAUDE = {
  limits: [
    { label: 'Current session', percent: 9, resets: 'Oct 28 at 9:39pm' },
    { label: 'Current week (all models)', percent: 92, resets: 'Oct 30 at 11am' },
  ],
  plan_note: '',
  details: '',
  raw: '',
  error: null,
  fetched_at: 0,
}

describe('AgentPicker', () => {
  it('shows each agent with its usage and picks one', async () => {
    mockApi({
      'GET /claude-usage': CLAUDE,
      'GET /cursor-usage': { plan: 'Team', limits: [], on_demand: null, message: '', error: 'Cursor login expired', fetched_at: 0 },
    })
    const onChange = vi.fn()
    renderApp(<AgentPicker agents={['claude', 'cursor']} value="claude" onChange={onChange} />)
    const claude = screen.getByRole('radio', { name: 'claude' })
    expect(claude).toHaveAttribute('aria-checked', 'true')
    expect(await within(claude).findByRole('progressbar', { name: 'Current week (all models)' })).toHaveAttribute(
      'aria-valuenow',
      '92',
    )
    expect(within(claude).getByText('week (all models)')).toBeInTheDocument()
    const cursor = screen.getByRole('radio', { name: 'cursor' })
    expect(await within(cursor).findByText('Cursor login expired')).toBeInTheDocument()
    await userEvent.click(cursor)
    expect(onChange).toHaveBeenCalledWith('cursor')
  })
})
