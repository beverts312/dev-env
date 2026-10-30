import { Eye, FolderGit2, Gauge, GitPullRequest, ListTodo, Mail, Settings, type LucideIcon } from 'lucide-react'

import type { TableId } from '@/lib/api'

// what a page's sidebar badge counts: its tables' rows
export type CountId = TableId

// the pages, in order; the number keys and t switch between them, and the sidebar lists all but home
export const PAGES: { path: string; label: string; icon: LucideIcon; tables: CountId[] }[] = [
  { path: '/', label: 'home', icon: ListTodo, tables: ['jira'] },
  { path: '/prs', label: 'my PRs', icon: GitPullRequest, tables: ['mine'] },
  { path: '/reviews', label: 'reviews', icon: Eye, tables: ['review', 'team'] },
  { path: '/workspaces', label: 'workspaces', icon: FolderGit2, tables: ['workspaces'] },
  { path: '/mail', label: 'mail', icon: Mail, tables: [] },
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
  ['enter', 'review, open the issue’s workspace, open the workspace, edit the todo, or read the email'],
  ['o', 'open in the browser'],
  ['r', 'mark your draft ready'],
  ['u', 'enable auto-merge on your PR'],
  ['d', 'delete the email (to Trash)'],
  ['x', 'check your PR for bulk actions, check off the todo, or select the email'],
  ['s', 'star or unstar the PR'],
  ['h / l', 'close or open a Jira issue’s children'],
  ['m', 'switch table'],
  ['c', 'collapse the table'],
  ['a', 'toggle filters'],
  ['/', 'search repo or title'],
  ['t or 1–7', 'switch page'],
  ['?', 'show these keys'],
]
