import { describe, expect, it } from 'vitest'

import type { Issue, Pr } from '@/lib/api'
import { countTree, filterTree, PR_DEFAULTS, prShown, toggleAll } from '@/lib/filters'

const pr = (over: Partial<Pr>): Pr => ({
  number: 1,
  repo: 'acme/api',
  title: 'Fix login',
  checks: 'pass',
  approvals: 0,
  draft: false,
  author: 'dev',
  approved: false,
  auto_merge: false,
  url: '',
  renovate: false,
  ...over,
})

describe('prShown', () => {
  it('shows what pr ls does by default', () => {
    expect(prShown(pr({}), PR_DEFAULTS, false)).toBe(true)
    expect(prShown(pr({ checks: 'fail' }), PR_DEFAULTS, false)).toBe(false)
    expect(prShown(pr({ draft: true }), PR_DEFAULTS, false)).toBe(false)
    expect(prShown(pr({ renovate: true }), PR_DEFAULTS, false)).toBe(false)
    // your PRs are never by renovate
    expect(prShown(pr({ renovate: true }), PR_DEFAULTS, true)).toBe(true)
  })

  it('searches repo and title, ignoring case', () => {
    expect(prShown(pr({}), { ...PR_DEFAULTS, search: ' LOGIN ' }, false)).toBe(true)
    expect(prShown(pr({}), { ...PR_DEFAULTS, search: 'acme/api fix' }, false)).toBe(true)
    expect(prShown(pr({}), { ...PR_DEFAULTS, search: 'web' }, false)).toBe(false)
  })

  it('toggles every filter off, then back to the defaults, keeping the search', () => {
    const off = toggleAll({ ...PR_DEFAULTS, search: 'x' })
    expect(off).toEqual({ checks: 'all', draft: 'all', renovate: false, search: 'x' })
    expect(prShown(pr({ checks: 'fail', draft: true, renovate: true, title: 'x' }), off, false)).toBe(true)
    expect(toggleAll(off)).toEqual({ ...PR_DEFAULTS, search: 'x' })
  })
})

const issue = (key: string, over: Partial<Issue> = {}, children: Issue[] = []): Issue => ({
  key,
  type: 'Story',
  summary: key,
  status: 'In Progress',
  category: 'indeterminate',
  assignee: 'Me',
  parent: '',
  parent_type: '',
  parent_summary: '',
  mine: true,
  url: '',
  project: key.split('-')[0],
  workspace: '',
  parent_offer: false,
  children,
  ...over,
})

describe('filterTree', () => {
  const tree = [
    issue('ACME-1', {}, [issue('ACME-2', { status: 'To Do' }), issue('ACME-3')]),
    issue('OPS-1', { status: 'To Do' }),
  ]

  it('shows everything with nothing picked', () => {
    expect(countTree(filterTree(tree, { project: [], status: [] }))).toBe(4)
  })

  it('keeps a parent that holds a match, dimmed', () => {
    const shown = filterTree(tree, { project: [], status: ['To Do'] })
    expect(shown.map((n) => [n.issue.key, n.context])).toEqual([
      ['ACME-1', true],
      ['OPS-1', false],
    ])
    expect(shown[0].children.map((n) => n.issue.key)).toEqual(['ACME-2'])
  })

  it('matches every filter with something picked', () => {
    const shown = filterTree(tree, { project: ['ACME'], status: ['To Do'] })
    expect(countTree(shown)).toBe(2)
  })
})
