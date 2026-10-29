import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PrTable, StarredTable } from '@/components/PrTable'
import type { Pr } from '@/lib/api'
import { readPersistent, writePersistent } from '@/lib/store'
import { mockApi, renderApp } from '@/test/render'

const pr = (number: number, over: Partial<Pr> = {}): Pr => ({
  number,
  repo: 'acme/api',
  title: `PR ${number}`,
  checks: 'pass',
  approvals: 1,
  draft: false,
  author: 'me',
  approved: false,
  auto_merge: false,
  url: `https://github.com/acme/api/pull/${number}`,
  renovate: false,
  actions: ['automerge'],
  ...over,
})

const MINE = [
  pr(7, { approved: true, actions: ['automerge', 'merge'] }),
  pr(8),
  pr(9, { draft: true, actions: ['ready'] }),
  pr(10, { checks: 'fail' }),
]

const table = (rows: Pr[] | null) => ({ table: 'mine', rows, error: null, empty: 'no open PRs by you' })

describe('PrTable', () => {
  it('filters as pr ls does, until told to show all', async () => {
    mockApi({ 'GET /tables/mine': table(MINE) })
    renderApp(<PrTable table="mine" title="your PRs" />)
    expect(await screen.findByText('PR 7')).toBeInTheDocument()
    expect(screen.getByText('PR 8')).toBeInTheDocument()
    // a draft and a failing PR are hidden by default
    expect(screen.queryByText('PR 9')).not.toBeInTheDocument()
    expect(screen.queryByText('PR 10')).not.toBeInTheDocument()
    expect(screen.getByText('2 hidden')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'show all' }))
    expect(screen.getByText('PR 9')).toBeInTheDocument()
    expect(screen.getByText('PR 10')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('searchbox'), 'PR 1')
    expect(screen.queryByText('PR 9')).not.toBeInTheDocument()
    expect(screen.getByText('PR 10')).toBeInTheDocument()
  })

  it('counts the checked PRs each bulk action applies to', async () => {
    writePersistent('be.filters.mine', { checks: 'all', draft: 'all', renovate: false, search: '' })
    mockApi({ 'GET /tables/mine': table(MINE) })
    renderApp(<PrTable table="mine" title="your PRs" />)
    await screen.findByText('PR 7')
    const bulk = () => screen.getByTestId('picked-count').parentElement!
    expect(within(bulk()).getByRole('button', { name: 'auto-merge (0)' })).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: 'select acme/api#7' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'select acme/api#9' }))
    expect(screen.getByTestId('picked-count')).toHaveTextContent('2 selected')
    expect(within(bulk()).getByRole('button', { name: 'ready (1)' })).toBeEnabled()
    expect(within(bulk()).getByRole('button', { name: 'auto-merge (1)' })).toBeEnabled()
    expect(within(bulk()).getByRole('button', { name: 'merge (1)' })).toBeEnabled()
    await userEvent.click(screen.getByRole('checkbox', { name: 'select all shown' }))
    expect(screen.getByTestId('picked-count')).toHaveTextContent('4 selected')
    expect(within(bulk()).getByRole('button', { name: 'auto-merge (3)' })).toBeEnabled()
  })

  it('runs a bulk action on the checked PRs', async () => {
    const calls = mockApi({
      'GET /tables/mine': table(MINE),
      'POST /prs/bulk': { message: 'ok', results: [{ pr: 'acme/api#8', ok: true, message: 'ok' }] },
    })
    renderApp(<PrTable table="mine" title="your PRs" />)
    await screen.findByText('PR 8')
    await userEvent.click(screen.getByRole('checkbox', { name: 'select acme/api#8' }))
    await userEvent.click(screen.getByRole('button', { name: 'auto-merge (1)' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')).toEqual({
      method: 'POST',
      path: '/prs/bulk',
      body: { action: 'automerge', prs: ['acme/api#8'] },
    })
  })

  it('offers to load a table that is not loaded yet', async () => {
    const calls = mockApi({ 'GET /tables/mine': table(null), 'GET /tables/mine?refresh=true': table(MINE) })
    renderApp(<PrTable table="mine" title="your PRs" />)
    await userEvent.click(await screen.findByRole('button', { name: 'load' }))
    expect(await screen.findByText('PR 7')).toBeInTheDocument()
    expect(calls.map((c) => c.path).filter((p) => p.startsWith('/tables'))).toEqual(['/tables/mine', '/tables/mine?refresh=true'])
  })

  it('stars a PR into the starred table, without your PR actions', async () => {
    mockApi({
      'GET /tables/mine': table(MINE),
      'POST /prs/starred': { rows: [pr(7, { title: 'PR 7 now', actions: undefined })], merged: [], error: null },
    })
    renderApp(
      <>
        <PrTable table="mine" title="your PRs" />
        <StarredTable title="starred" />
      </>,
    )
    expect(await screen.findByText('no starred PRs; star one from your PRs or reviews')).toBeInTheDocument()
    await screen.findByText('PR 7')
    await userEvent.click(screen.getByRole('button', { name: 'star acme/api#7' }))
    // the fresh row from GitHub replaces the one starred
    expect(await screen.findByText('PR 7 now')).toBeInTheDocument()
    const starred = within(screen.getByText('starred').closest('section')!)
    expect(starred.queryByRole('button', { name: 'auto-merge' })).not.toBeInTheDocument()
    expect(readPersistent<Pr[]>('be.starred', [])[0].actions).toBeUndefined()
  })

  it('drops merged PRs and unstars', async () => {
    writePersistent('be.starred', [pr(7), pr(8)])
    const calls = mockApi({ 'POST /prs/starred': { rows: [pr(8)], merged: ['acme/api#7'], error: null } })
    renderApp(<StarredTable title="starred" />)
    await waitFor(() => expect(screen.queryByText('PR 7')).not.toBeInTheDocument())
    expect(screen.getByText('PR 8')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/prs/starred')?.body).toEqual({ prs: ['acme/api#7', 'acme/api#8'] })
    expect(readPersistent<Pr[]>('be.starred', []).map((p) => p.number)).toEqual([8])
    await userEvent.click(screen.getByRole('button', { name: 'unstar acme/api#8' }))
    expect(await screen.findByText('no starred PRs; star one from your PRs or reviews')).toBeInTheDocument()
    expect(readPersistent<Pr[]>('be.starred', [])).toEqual([])
  })
})
