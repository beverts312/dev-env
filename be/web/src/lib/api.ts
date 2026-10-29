// The client for `be server`'s JSON API (be/src/be/server/api.py). Every error answers
// {message}: 400 for bad input, 422 for an action that ran and failed.

export type MineAction = 'ready' | 'automerge' | 'merge'

export const ACTION_LABELS: Record<MineAction, string> = { ready: 'ready', automerge: 'auto-merge', merge: 'merge' }

export type Pr = {
  number: number
  repo: string
  title: string
  checks: string
  approvals: number
  draft: boolean
  author: string
  approved: boolean
  auto_merge: boolean
  url: string
  renovate: boolean
  // only on your PRs: what can be done to it now
  actions?: MineAction[]
}

export type Issue = {
  key: string
  type: string
  summary: string
  status: string
  // the status category's key: new, indeterminate or done
  category: string
  assignee: string
  parent: string
  parent_type: string
  parent_summary: string
  mine: boolean
  url: string
  project: string
  // the workspace named after or linked to it or its parent, else ""
  workspace: string
  // whether a new workspace could be for its Feature or Epic parent instead
  parent_offer: boolean
  children: Issue[]
}

export type Workspace = {
  dir: string
  name: string
  description: string
  repos: string[]
  extra_dirs: string[]
  issue_name?: string
  issues?: string[]
}

export type TableId = 'review' | 'team' | 'mine' | 'jira' | 'workspaces'
export type PrTableId = 'review' | 'team' | 'mine'

type RowsOf = { review: Pr; team: Pr; mine: Pr; jira: Issue; workspaces: Workspace }

export type TableData<T extends TableId = TableId> = {
  table: T
  // null until a PR table is refreshed
  rows: RowsOf[T][] | null
  error: string | null
  // what an empty PR table says
  empty?: string
  // the Jira tree's filter options
  projects?: { key: string; note: string }[]
  statuses?: string[]
}

export type Meta = {
  agent: string
  agents: string[]
  config_path: string
}

export type Setting = {
  key: string
  env: string
  help: string
  default: string | null
  kind: string
  secret: boolean
  choices: string[]
  source: string
  notes: string[]
  value?: string
  entries?: Record<string, string>
}

export type ConfigData = { path: string; settings: Setting[]; error: string | null }

// one of the plan's limits, as `claude /usage` prints it
export type Limit = { label: string; percent: number; resets: string }

export type ClaudeUsage = {
  limits: Limit[]
  // which account pays: the subscription or an API key
  plan_note: string
  // what /usage says is behind the usage, as printed
  details: string
  raw: string
  error: string | null
  // seconds since the epoch
  fetched_at: number
}

// on-demand spend past the plan, as the Cursor agent's /usage shows it
export type OnDemand = {
  kind: 'fixed' | 'unlimited' | 'disabled' | 'unavailable'
  used_dollars: number
  // only when fixed
  limit_dollars: number | null
}

export type CursorUsage = {
  plan: string
  limits: Limit[]
  on_demand: OnDemand | null
  // why there are no limits, when there aren't
  message: string
  error: string | null
  // seconds since the epoch
  fetched_at: number
}

export type Done = { message: string }
export type BulkDone = Done & { results: { pr: string; ok: boolean; message: string }[] }

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(data.message ?? res.statusText, res.status)
  return data as T
}

const segment = encodeURIComponent

export const api = {
  meta: () => request<Meta>('GET', '/meta'),
  table: <T extends TableId>(table: T, refresh = false) =>
    request<TableData<T>>('GET', `/tables/${table}${refresh ? '?refresh=true' : ''}`),
  review: (repo: string, number: number, agent: string) =>
    request<Done>('POST', '/prs/review', { repo, number, agent }),
  mineAction: (action: MineAction, repo: string, number: number) =>
    request<Done>('POST', `/prs/${action}`, { repo, number }),
  bulk: (action: MineAction, prs: string[]) => request<BulkDone>('POST', '/prs/bulk', { action, prs }),
  openWorkspace: (name: string) => request<Done>('POST', `/workspaces/${segment(name)}/open`),
  createWorkspace: (fields: {
    name: string
    repos: string
    extra_dirs: string
    description: string
    issue_name: string
  }) => request<Done>('POST', '/workspaces', fields),
  linkWorkspace: (name: string, key: string) =>
    request<Done>('POST', `/workspaces/${segment(name)}/link`, { key }),
  config: () => request<ConfigData>('GET', '/config'),
  setConfig: (key: string, value: string, name = '') =>
    request<Done>('PUT', `/config/${segment(key)}`, { value, name }),
  unsetConfig: (key: string) => request<Done>('DELETE', `/config/${segment(key)}`),
  claudeUsage: () => request<ClaudeUsage>('GET', '/claude-usage'),
  cursorUsage: () => request<CursorUsage>('GET', '/cursor-usage'),
}

export const prName = (p: Pr) => `${p.repo}#${p.number}`
