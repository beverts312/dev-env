import type { Issue, Pr, PrViewId } from '@/lib/api'
import { usePersistent } from '@/lib/store'

// the PR tables' filters, defaulting to what `pr ls` shows: passing checks, not drafts, not by Renovate
export type PrFilters = { checks: string; draft: string; renovate: boolean; search: string }

export const ALL = 'all'
export const CHECKS = ['pass', 'fail', 'pending', 'none']
export const DRAFT = ['no', 'yes']
export const PR_DEFAULTS: PrFilters = { checks: 'pass', draft: 'no', renovate: true, search: '' }

export function usePrFilters(table: PrViewId) {
  return usePersistent<PrFilters>(`be.filters.${table}`, PR_DEFAULTS)
}

export function prShown(p: Pr, f: PrFilters, mine: boolean): boolean {
  // your PRs are never by Renovate, so they skip that filter
  if (!mine && f.renovate && p.renovate) return false
  if (f.checks !== ALL && p.checks !== f.checks) return false
  if (f.draft !== ALL && (p.draft ? 'yes' : 'no') !== f.draft) return false
  const text = f.search.trim().toLowerCase()
  return !text || `${p.repo} ${p.title}`.toLowerCase().includes(text)
}

export const filtersOn = (f: PrFilters) => f.renovate || f.checks !== ALL || f.draft !== ALL

// like --all: clear every filter, or turn them all back on; the search stays
export function toggleAll(f: PrFilters): PrFilters {
  return filtersOn(f)
    ? { ...f, checks: ALL, draft: ALL, renovate: false }
    : { ...PR_DEFAULTS, search: f.search }
}

// the Jira tree's filters: the issues in any checked project and status; none checked shows all
export type TreePicks = { project: string[]; status: string[] }
export const NO_PICKS: TreePicks = { project: [], status: [] }

export function useTreePicks() {
  return usePersistent<TreePicks>('be.filters.jira', NO_PICKS)
}

export type ShownIssue = {
  issue: Issue
  // shown dimmed because it doesn't match but holds an issue that does
  context: boolean
  children: ShownIssue[]
}

export function filterTree(issues: Issue[], picks: TreePicks): ShownIssue[] {
  const matches = (issue: Issue) =>
    (!picks.project.length || picks.project.includes(issue.project)) &&
    (!picks.status.length || picks.status.includes(issue.status))
  const walk = (issue: Issue): ShownIssue | null => {
    const children = issue.children.map(walk).filter((x): x is ShownIssue => x !== null)
    const match = matches(issue)
    if (!match && !children.length) return null
    return { issue, context: !match, children }
  }
  return issues.map(walk).filter((x): x is ShownIssue => x !== null)
}

export function countTree(issues: { children: unknown[] }[]): number {
  return issues.reduce((n, issue) => n + 1 + countTree(issue.children as { children: unknown[] }[]), 0)
}
