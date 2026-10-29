import { Eye, FolderGit2, Gauge, GitPullRequest, ListChecks, ListTodo, Settings, type LucideIcon } from 'lucide-react'

import type { TableId } from '@/lib/api'

// what a page's sidebar badge counts: its tables' rows, or the open todos
export type CountId = TableId | 'todos'

// the sidebar's pages, in order; the number keys and t switch between them
export const PAGES: { path: string; label: string; icon: LucideIcon; tables: CountId[] }[] = [
  { path: '/', label: 'my work', icon: ListTodo, tables: ['jira'] },
  { path: '/todos', label: 'todos', icon: ListChecks, tables: ['todos'] },
  { path: '/prs', label: 'my PRs', icon: GitPullRequest, tables: ['mine'] },
  { path: '/reviews', label: 'reviews', icon: Eye, tables: ['review', 'team'] },
  { path: '/workspaces', label: 'workspaces', icon: FolderGit2, tables: ['workspaces'] },
  { path: '/usage', label: 'usage', icon: Gauge, tables: [] },
  { path: '/config', label: 'config', icon: Settings, tables: [] },
]

export const TITLES: Record<string, string> = {
  review: 'review requests',
  team: 'team review requests',
  mine: 'your PRs',
  starred: 'starred',
}

export const KEYS: [string, string][] = [
  ['j / k', 'move between rows'],
  ['enter', 'review, open the issue’s workspace, open the workspace, or edit the todo'],
  ['o', 'open in the browser'],
  ['r', 'mark your draft ready'],
  ['u', 'enable auto-merge on your PR'],
  ['x', 'check your PR for bulk actions, or check off the todo'],
  ['s', 'star or unstar the PR'],
  ['h / l', 'close or open a Jira issue’s children'],
  ['m', 'switch table'],
  ['c', 'collapse the table'],
  ['a', 'toggle filters'],
  ['/', 'search repo or title'],
  ['t or 1–7', 'switch page'],
  ['?', 'show these keys'],
]
