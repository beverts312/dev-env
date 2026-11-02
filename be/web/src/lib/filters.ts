import type { Issue, Pr, PrViewId } from '@/lib/api'
import { usePersistent } from '@/lib/store'

// the PR tables' filters, defaulting to what `pr ls` shows: passing checks, not drafts, not by Renovate.
// authors shows only the PRs by any checked author; none checked shows all
export type PrFilters = { checks: string; draft: string; renovate: boolean; search: string; authors?: string[] }

export const ALL = 'all'
export const CHECKS = ['pass', 'fail', 'pending', 'none']
export const DRAFT = ['no', 'yes']
// the badge colors for each checks state; none has none
export const CHECK_STYLES: Record<string, string> = {
  pass: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  fail: 'bg-red-500/15 text-red-600 dark:text-red-400',
  pending: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
}

export const PR_DEFAULTS: PrFilters = { checks: 'pass', draft: 'no', renovate: true, search: '' }

export function usePrFilters(table: PrViewId) {
  return usePersistent<PrFilters>(`be.filters.${table}`, PR_DEFAULTS)
}

export function prShown(p: Pr, f: PrFilters, mine: boolean): boolean {
  // your PRs are never by Renovate, so they skip that filter
  if (!mine && f.renovate && p.renovate) return false
  if (f.checks !== ALL && p.checks !== f.checks) return false
  if (f.draft !== ALL && (p.draft ? 'yes' : 'no') !== f.draft) return false
  if (f.authors?.length && !f.authors.includes(p.author)) return false
  const text = f.search.trim().toLowerCase()
  return !text || `${p.repo} ${p.title}`.toLowerCase().includes(text)
}

export const filtersOn = (f: PrFilters) => f.renovate || f.checks !== ALL || f.draft !== ALL

// like --all: clear every filter, or turn them all back on; the search and authors stay
export function toggleAll(f: PrFilters): PrFilters {
  return filtersOn(f)
    ? { ...f, checks: ALL, draft: ALL, renovate: false }
    : { ...PR_DEFAULTS, search: f.search, authors: f.authors }
}

// the Jira tree's filters: the issues in any checked project and status; none checked shows all.
// mine hides the issues assigned to someone else, keeping them only as context; noPrs hides the issues' PRs
export type TreePicks = { project: string[]; status: string[]; mine?: boolean; noPrs?: boolean }
export const NO_PICKS: TreePicks = { project: [], status: [], mine: false, noPrs: false }

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
    (!picks.status.length || picks.status.includes(issue.status)) &&
    (!picks.mine || issue.mine)
  const walk = (issue: Issue): ShownIssue | null => {
    const children = issue.children.map(walk).filter((x): x is ShownIssue => x !== null)
    const match = matches(issue)
    if (!match && !children.length) return null
    return { issue: picks.noPrs ? { ...issue, prs: [] } : issue, context: !match, children }
  }
  return issues.map(walk).filter((x): x is ShownIssue => x !== null)
}

export function countTree(issues: { children: unknown[] }[]): number {
  return issues.reduce((n, issue) => n + 1 + countTree(issue.children as { children: unknown[] }[]), 0)
}
