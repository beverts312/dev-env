import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { MailThread } from '@/lib/api'
import { Mail } from '@/pages/Mail'
import { mockApi, renderApp } from '@/test/render'

function thread(id: string, fields: Partial<MailThread> = {}): MailThread {
  return {
    id,
    from: 'Pat Lee <pat@x.com>',
    subject: `subject ${id}`,
    snippet: 'can you look?',
    date: String(Date.now()),
    unread: false,
    labels: ['INBOX'],
    count: 1,
    ...fields,
  }
}

const list = (threads: MailThread[], error: string | null = null) => ({ threads, next_page: null, error, fetched_at: 0 })
const inbox = `GET /mail?q=${encodeURIComponent('in:inbox')}`
const actions = { actions: [{ key: 'summarize', label: 'Summarize', prompt: 'Summarize.' }] }
const detail = {
  id: 't1',
  subject: 'subject t1',
  messages: [
    { id: 'm1', from: 'Pat Lee <pat@x.com>', to: 'me@x.com', cc: '', subject: 'subject t1', date: '', date_ms: '0', unread: true, text: 'numbers attached', html: '' },
  ],
}

describe('Mail', () => {
  it('lists the inbox, opens a thread, marks it read and runs claude on it', async () => {
    const calls = mockApi({
      [inbox]: list([thread('t1', { unread: true })]),
      'GET /mail/actions': actions,
      'GET /mail/t1': detail,
      'POST /mail/t1/modify': { message: 'updated the thread' },
      'POST /mail/t1/action': { message: 'opened claude: summarize' },
    })
    renderApp(<Mail />)
    await userEvent.click(await screen.findByText('subject t1', { selector: 'div' }))
    expect(await screen.findByText('numbers attached')).toBeInTheDocument()
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/t1/modify', body: { remove: ['UNREAD'] } }),
    )

    await userEvent.click(screen.getByRole('button', { name: 'claude' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Summarize' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/t1/action', body: { action: 'summarize' } }),
    )

    await userEvent.type(screen.getByRole('textbox', { name: 'ask claude' }), 'who is Pat?{enter}')
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/t1/action', body: { prompt: 'who is Pat?' } }),
    )
  })

  it('deletes from the list', async () => {
    const calls = mockApi({ [inbox]: list([thread('t1')]), 'POST /mail/t1/trash': { message: 'moved the thread to Trash' } })
    renderApp(<Mail />)
    await userEvent.click(await screen.findByRole('button', { name: 'delete subject t1' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/t1/trash', body: undefined }),
    )
  })

  it('shows why mail could not be read', async () => {
    mockApi({ [inbox]: list([], 'not signed in to Google; run `be calendar login`') })
    renderApp(<Mail />)
    expect(await screen.findByText(/be calendar login/)).toBeInTheDocument()
  })
})

describe('Mail read filter', () => {
  it('adds is:unread or is:read to the query', async () => {
    const calls = mockApi({
      [inbox]: list([thread('t1')]),
      [`GET /mail?q=${encodeURIComponent('in:inbox is:unread')}`]: list([thread('t2', { unread: true })]),
    })
    renderApp(<Mail />)
    await screen.findByText('subject t1', { selector: 'div' })
    await userEvent.click(screen.getByRole('radio', { name: 'unread' }))
    expect(await screen.findByText('subject t2', { selector: 'div' })).toBeInTheDocument()
    expect(calls.map((c) => c.path)).toContain(`/mail?q=${encodeURIComponent('in:inbox is:unread')}`)
  })
})

describe('Mail rows', () => {
  it('mark which emails are unread', async () => {
    mockApi({ [inbox]: list([thread('t1', { unread: true }), thread('t2')]) })
    renderApp(<Mail />)
    const unread = (await screen.findByText('subject t1', { selector: 'div' })).closest('li')
    const read = screen.getByText('subject t2', { selector: 'div' }).closest('li')
    expect(unread).toHaveAttribute('data-unread', 'true')
    expect(unread).toHaveTextContent(/^unread/)
    expect(read).toHaveAttribute('data-unread', 'false')
    expect(read).toHaveTextContent(/^read/)
  })
})

describe('Mail row claude menu', () => {
  it('runs an action on the row’s thread without opening it', async () => {
    const calls = mockApi({
      [inbox]: list([thread('t1')]),
      'GET /mail/actions': actions,
      'POST /mail/t1/action': { message: 'opened claude: summarize' },
    })
    renderApp(<Mail />)
    await userEvent.click(await screen.findByRole('button', { name: 'claude on subject t1' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Summarize' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/t1/action', body: { action: 'summarize' } }),
    )
    expect(screen.getByText('pick an email')).toBeInTheDocument()
  })
})

describe('Mail multi-select', () => {
  it('checks threads, shift-clicks a range and deletes them together', async () => {
    const calls = mockApi({
      [inbox]: list([thread('t1'), thread('t2'), thread('t3'), thread('t4')]),
      'POST /mail/trash': { message: 'moved 3 threads to Trash' },
    })
    renderApp(<Mail />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'select subject t1' }))
    const user = userEvent.setup()
    await user.keyboard('{Shift>}')
    await user.click(screen.getByRole('checkbox', { name: 'select subject t3' }))
    await user.keyboard('{/Shift}')
    expect(screen.getByText('3 selected')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'select all' })).toHaveAttribute('data-state', 'indeterminate')
    await userEvent.click(screen.getByRole('button', { name: 'delete 3' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/mail/trash', body: { ids: ['t1', 't2', 't3'] } }),
    )
    await waitFor(() => expect(screen.queryByText('3 selected')).not.toBeInTheDocument())
  })

  it('selects all and clears', async () => {
    mockApi({ [inbox]: list([thread('t1'), thread('t2')]) })
    renderApp(<Mail />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'select all' }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'clear' }))
    expect(screen.queryByText('2 selected')).not.toBeInTheDocument()
  })
})
