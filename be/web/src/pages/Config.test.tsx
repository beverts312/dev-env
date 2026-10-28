import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Setting } from '@/lib/api'
import { Config } from '@/pages/Config'
import { mockApi, renderApp } from '@/test/render'

const setting = (over: Partial<Setting>): Setting => ({
  key: 'git.name',
  env: 'GIT_NAME',
  help: 'Your name',
  default: null,
  kind: 'str',
  secret: false,
  choices: [],
  source: 'file',
  notes: [],
  value: 'Me',
  ...over,
})

const CONFIG = {
  path: '/home/me/.be/config',
  error: null,
  settings: [
    setting({}),
    setting({ key: 'jira.token', secret: true, value: 'hunter2', notes: ['JIRA_API_TOKEN overrides the file: ********'] }),
    setting({ key: 'jira.projects', kind: 'map', value: undefined, entries: { ACME: 'Acme' } }),
  ],
}

describe('Config', () => {
  it('saves and unsets a setting', async () => {
    const calls = mockApi({
      'GET /config': CONFIG,
      'GET /meta': { agent: 'claude', agents: ['claude', 'cursor'], config_path: CONFIG.path },
      'PUT /config/git.name': { message: 'saved git.name' },
      'DELETE /config/git.name': { message: 'removed git.name' },
    })
    renderApp(<Config />)
    const input = await screen.findByRole('textbox', { name: 'git.name' })
    expect(screen.getByText('/home/me/.be/config')).toBeInTheDocument()
    await userEvent.clear(input)
    await userEvent.type(input, 'Someone')
    await userEvent.click(screen.getAllByRole('button', { name: 'save' })[0])
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(calls.find((c) => c.method === 'PUT')).toEqual({
      method: 'PUT',
      path: '/config/git.name',
      body: { value: 'Someone', name: '' },
    })
    await userEvent.click(screen.getAllByRole('button', { name: 'unset' })[0])
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/config/git.name')).toBe(true))
  })

  it('hides a secret until shown, and says what overrides it', async () => {
    mockApi({ 'GET /config': CONFIG })
    renderApp(<Config />)
    const token = await screen.findByLabelText('jira.token')
    expect(token).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'show' }))
    expect(token).toHaveAttribute('type', 'text')
    expect(screen.getByText('JIRA_API_TOKEN overrides the file: ********')).toBeInTheDocument()
  })

  it('adds an entry to a map setting', async () => {
    const calls = mockApi({ 'GET /config': CONFIG, 'PUT /config/jira.projects': { message: 'saved jira.projects.OPS' } })
    renderApp(<Config />)
    expect(await screen.findByDisplayValue('Acme')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'new jira.projects name' }), 'OPS')
    await userEvent.type(screen.getByRole('textbox', { name: 'new jira.projects description' }), 'Operations')
    await userEvent.click(screen.getByRole('button', { name: 'add' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ value: 'Operations', name: 'OPS' }),
    )
  })
})
