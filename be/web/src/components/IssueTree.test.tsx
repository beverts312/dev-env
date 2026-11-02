import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { IssueTree } from '@/components/IssueTree'
import type { Issue, Pr } from '@/lib/api'
import { mockApi, renderApp } from '@/test/render'

const pr = (number: number, over: Partial<Pr> = {}): Pr => ({
  number,
  repo: 'acme/api',
  title: `PR ${number}`,
  checks: 'pass',
  approvals: 1,
  draft: false,
  author: 'dev',
  approved: false,
  auto_merge: false,
  url: `https://github.com/acme/api/pull/${number}`,
  renovate: false,
  ...over,
})

const issue = (key: string, over: Partial<Issue> = {}): Issue => ({
  key,
  type: 'Story',
  summary: `summary ${key}`,
  status: 'In Progress',
  category: 'indeterminate',
  assignee: 'Me',
  parent: '',
  parent_type: '',
  parent_summary: '',
  mine: true,
  url: '',
  project: 'ACME',
  workspace: '',
  parent_offer: false,
  prs: [],
  children: [],
  ...over,
})

const ROWS = [
  issue('ACME-1', { type: 'Feature', children: [issue('ACME-2', { prs: [pr(7)] })] }),
  issue('ACME-3', { prs: [pr(8, { draft: true, checks: 'fail' })] }),
]

const routes = {
  'GET /tables/jira': { table: 'jira', rows: ROWS, error: null, projects: [], statuses: [] },
  'GET /tables/workspaces': { table: 'workspaces', rows: [], error: null },
}

describe('IssueTree', () => {
  it('lists open PRs under their issues', async () => {
    mockApi(routes)
    renderApp(<IssueTree />)
    const link = await screen.findByRole('link', { name: 'acme/api#7' })
    expect(link).toHaveAttribute('href', 'https://github.com/acme/api/pull/7')
    expect(screen.getByText('PR 7')).toBeInTheDocument()
    expect(screen.getByText('draft')).toBeInTheDocument()
    // each PR is a leaf of the tree
    expect(screen.getByText('PR 8').closest('li')).toHaveAttribute('role', 'treeitem')
  })

  it('makes an issue with only PRs collapsible', async () => {
    mockApi(routes)
    renderApp(<IssueTree />)
    await screen.findByText('PR 8')
    await userEvent.click(screen.getByRole('button', { name: 'collapse ACME-3' }))
    expect(screen.queryByText('PR 8')).not.toBeInTheDocument()
    expect(screen.getByText('PR 7')).toBeInTheDocument()
  })

  it('hides PRs when asked', async () => {
    mockApi(routes)
    renderApp(<IssueTree />)
    await screen.findByText('PR 8')
    await userEvent.click(screen.getByRole('checkbox', { name: 'hide PRs' }))
    expect(screen.queryByText('PR 7')).not.toBeInTheDocument()
    expect(screen.queryByText('PR 8')).not.toBeInTheDocument()
    // an issue left with nothing under it can't be expanded
    expect(screen.queryByRole('button', { name: 'collapse ACME-3' })).not.toBeInTheDocument()
    expect(screen.getByText('summary ACME-2')).toBeInTheDocument()
  })
})
