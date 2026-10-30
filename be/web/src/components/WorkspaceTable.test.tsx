import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { WorkspaceTable } from '@/components/WorkspaceTable'
import { mockApi, renderApp } from '@/test/render'

const DATA = {
  rows: [{ dir: 'proj', name: 'proj', description: '', repos: ['api'], extra_dirs: [] }],
  error: null,
}

describe('WorkspaceTable', () => {
  it('deletes a workspace after confirming', async () => {
    const calls = mockApi({
      'GET /tables/workspaces': DATA,
      'DELETE /workspaces/proj': { message: 'deleted proj' },
    })
    renderApp(<WorkspaceTable />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'delete proj' }))
    expect(screen.getByText(/its clones of api with any unpushed work/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'delete' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/workspaces/proj')).toBe(true))
  })

  it('opens the sessions dialog', async () => {
    mockApi({ 'GET /tables/workspaces': DATA, 'GET /workspaces/proj/sessions': { sessions: [] } })
    renderApp(<WorkspaceTable />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'sessions' }))
    expect(await screen.findByText('no sessions')).toBeInTheDocument()
  })

  it('opens a workspace in VS Code', async () => {
    const calls = mockApi({ 'GET /tables/workspaces': DATA, 'POST /workspaces/proj/vscode': { message: 'opened proj in VS Code' } })
    renderApp(<WorkspaceTable />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'vscode' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workspaces/proj/vscode')).toBe(true))
  })
})
