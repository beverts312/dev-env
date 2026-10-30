import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { ClaudeSession } from '@/lib/api'
import { SessionsDialog } from '@/components/SessionsDialog'
import { mockApi, renderApp } from '@/test/render'

const session = (fields: Partial<ClaudeSession>): ClaudeSession => ({
  id: 'a1',
  title: 'x',
  last_prompt: '',
  cwd: '/ws/proj',
  subdir: '',
  updated: '2026-10-28T12:00:00+00:00',
  size: 10,
  ...fields,
})

const SESSIONS = {
  sessions: [
    session({ id: 'a1', title: 'Fix login', last_prompt: 'commit it' }),
    session({ id: 'b2', title: 'run tests', last_prompt: 'run tests', subdir: 'api' }),
  ],
}

describe('SessionsDialog', () => {
  it('lists the sessions with their last prompt and folder', async () => {
    mockApi({ 'GET /workspaces/proj/sessions': SESSIONS })
    renderApp(<SessionsDialog workspace="proj" onClose={() => {}} />)
    expect(await screen.findByText('Fix login')).toBeInTheDocument()
    expect(screen.getByText('commit it')).toBeInTheDocument()
    expect(screen.getByText('api')).toBeInTheDocument()
  })

  it('says when there are none', async () => {
    mockApi({ 'GET /workspaces/proj/sessions': { sessions: [] } })
    renderApp(<SessionsDialog workspace="proj" onClose={() => {}} />)
    expect(await screen.findByText('no sessions')).toBeInTheDocument()
  })

  it('resumes a session and closes', async () => {
    const calls = mockApi({
      'GET /workspaces/proj/sessions': SESSIONS,
      'POST /workspaces/proj/sessions/a1/resume': { message: 'resumed Fix login' },
    })
    let closed = false
    renderApp(<SessionsDialog workspace="proj" onClose={() => (closed = true)} />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'resume Fix login' }))
    await waitFor(() => expect(closed).toBe(true))
    expect(calls.some((c) => c.method === 'POST' && c.path === '/workspaces/proj/sessions/a1/resume')).toBe(true)
  })

  it('deletes a session after confirming', async () => {
    const calls = mockApi({
      'GET /workspaces/proj/sessions': SESSIONS,
      'DELETE /workspaces/proj/sessions/b2': { message: 'deleted run tests' },
    })
    renderApp(<SessionsDialog workspace="proj" onClose={() => {}} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'delete run tests' }))
    await user.click(screen.getByRole('button', { name: 'delete' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(calls.find((c) => c.method === 'DELETE')?.path).toBe('/workspaces/proj/sessions/b2')
  })
})
