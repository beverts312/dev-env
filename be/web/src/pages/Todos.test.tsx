import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Todo, TodosData } from '@/lib/api'
import { Todos } from '@/pages/Todos'
import { mockApi, renderApp } from '@/test/render'

const todo = (fields: Partial<Todo>): Todo => ({
  id: 'x',
  title: 'x',
  status: 'open',
  priority: null,
  due: null,
  created: '2026-10-28',
  completed: null,
  jira: null,
  url: '',
  tags: [],
  notes: '',
  overdue: false,
  ...fields,
})

const DATA: TodosData = {
  rows: [
    todo({ id: 'renew-cert', title: 'Renew cert', due: '2026-01-01', overdue: true, priority: 'high', jira: 'ADC-1', url: 'https://acme.atlassian.net/browse/ADC-1', tags: ['infra'], notes: 'see runbook' }),
    todo({ id: 'buy-milk', title: 'Buy milk', tags: ['home'] }),
  ],
  error: null,
  dir: '/notes/todos',
}

describe('Todos', () => {
  it('shows each todo with its due date, priority, Jira link and tags', async () => {
    mockApi({ 'GET /todos': DATA })
    renderApp(<Todos />)
    expect(await screen.findByRole('button', { name: 'Renew cert' })).toBeInTheDocument()
    expect(screen.getByText('2026-01-01')).toHaveClass('text-destructive')
    expect(screen.getByText('see runbook')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ADC-1/ })).toHaveAttribute('href', 'https://acme.atlassian.net/browse/ADC-1')
    expect(screen.getByText('/notes/todos')).toBeInTheDocument()
  })

  it('adds a todo by title and checks one off', async () => {
    const calls = mockApi({
      'GET /todos': DATA,
      'POST /todos': { message: 'added Call bob', todo: todo({ id: 'call-bob', title: 'Call bob' }) },
      'POST /todos/buy-milk/done': { message: 'done Buy milk', todo: todo({ id: 'buy-milk', status: 'done' }) },
    })
    renderApp(<Todos />)
    const user = userEvent.setup()
    await user.type(await screen.findByRole('textbox', { name: 'new todo' }), 'Call bob{Enter}')
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/todos')).toBe(true))
    expect(calls.find((c) => c.path === '/todos' && c.method === 'POST')?.body).toEqual({ title: 'Call bob' })
    await user.click(screen.getByRole('checkbox', { name: 'check off Buy milk' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/todos/buy-milk/done')).toBe(true))
  })

  it('edits a todo in its dialog', async () => {
    const calls = mockApi({
      'GET /todos': DATA,
      'PUT /todos/buy-milk': { message: 'saved Buy milk', todo: todo({ id: 'buy-milk' }) },
    })
    renderApp(<Todos />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Buy milk' }))
    await user.type(screen.getByLabelText('notes'), 'oat')
    await user.clear(screen.getByLabelText('tags'))
    await user.type(screen.getByLabelText('tags'), 'home, errands')
    await user.click(screen.getByRole('button', { name: 'save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
      title: 'Buy milk',
      due: '',
      priority: '',
      jira: '',
      tags: ['home', 'errands'],
      notes: 'oat',
    })
  })
})
