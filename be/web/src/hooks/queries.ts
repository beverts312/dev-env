import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, prName, type Done, type Pr, type TableId } from '@/lib/api'
import { usePersistent } from '@/lib/store'

export const tableKey = (table: TableId) => ['table', table] as const

// A table as the server has it: reading it doesn't fetch a PR table from GitHub; refresh does
export function useTable<T extends TableId>(table: T) {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: tableKey(table), queryFn: () => api.table(table) })
  const refresh = useMutation({
    mutationFn: () => api.table(table, true),
    onSuccess: (data) => qc.setQueryData(tableKey(table), data),
    onError: (e) => toast.error(e.message),
  })
  return { ...query, refresh: () => refresh.mutate(), refreshing: refresh.isPending }
}

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: api.meta, staleTime: Infinity })
}

// The PRs starred from your PRs or reviews, kept by the browser as they last looked, so the
// starred table draws without waiting on GitHub
export function useStarred() {
  const [starred, setStarred] = usePersistent<Pr[]>('be.starred', [])
  const isStarred = (p: Pr) => starred.some((s) => prName(s) === prName(p))
  const toggle = (p: Pr) =>
    setStarred((prev) =>
      prev.some((s) => prName(s) === prName(p)) ? prev.filter((s) => prName(s) !== prName(p)) : // your PR's actions are the my PRs page's; the starred table only reviews
          [...prev, { ...p, actions: undefined }],
    )
  return { starred, isStarred, toggle }
}

// The starred PRs, reread from GitHub when the table shows and on refresh: merged ones are unstarred,
// the rest saved as they are now
export function useStarredTable() {
  const [starred, setStarred] = usePersistent<Pr[]>('be.starred', [])
  const names = starred.map(prName).sort()
  const query = useQuery({
    queryKey: ['starred', names],
    queryFn: async () => {
      const data = await api.starred(names)
      if (data.rows) {
        const fresh = new Map(data.rows.map((p) => [prName(p), p]))
        // stars changed while this was asked keep theirs
        setStarred((prev) =>
          prev.filter((p) => !data.merged.includes(prName(p))).map((p) => ({ ...p, ...fresh.get(prName(p)) })),
        )
      }
      return data
    },
    enabled: names.length > 0,
    // the key changes as the fresh rows are saved; keep showing the last answer meanwhile
    placeholderData: (prev) => prev,
  })
  return {
    rows: starred,
    error: query.error?.message ?? (query.data?.error && `github: ${query.data.error}`) ?? null,
    refresh: () => void query.refetch(),
    refreshing: query.isFetching,
  }
}

// The reviews page's agent: the one last picked, else --agent or pr.agent
export function useAgent(): [string, (agent: string) => void] {
  const meta = useMeta()
  const [saved, setSaved] = usePersistent<string>('be.agent', '')
  const agents = meta.data?.agents ?? ['claude', 'cursor']
  return [agents.includes(saved) ? saved : (meta.data?.agent ?? 'claude'), setSaved]
}

// An action that toasts what happened, then rereads the tables (or other queries) it changes
export function useAction<A extends unknown[]>(
  run: (...args: A) => Promise<Done>,
  changes: (TableId | QueryKey)[] = [],
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: A) => run(...args),
    onSuccess: (done) => toast.success(done.message),
    onError: (e) => toast.error(e.message),
    onSettled: () =>
      Promise.all(
        changes.map((c) => qc.invalidateQueries({ queryKey: typeof c === 'string' ? tableKey(c) : c })),
      ),
  })
}

export const todosKey = ['todos'] as const

// The todos, read afresh from their files; with done, the done ones too
export function useTodos(done = false) {
  return useQuery({ queryKey: [...todosKey, done], queryFn: () => api.todos(done) })
}

export const sessionsKey = (workspace: string) => ['sessions', workspace] as const

// The claude sessions run in a workspace, read afresh from their transcripts
export function useSessions(workspace: string) {
  return useQuery({ queryKey: sessionsKey(workspace), queryFn: () => api.workspaceSessions(workspace) })
}

// how often plan usage is reread, on the usage page and the reviews page's agent picker
const USAGE_EVERY = 60_000

export function useClaudeUsage() {
  return useQuery({ queryKey: ['claude-usage'], queryFn: api.claudeUsage, refetchInterval: USAGE_EVERY })
}

export function useCursorUsage() {
  return useQuery({ queryKey: ['cursor-usage'], queryFn: api.cursorUsage, refetchInterval: USAGE_EVERY })
}

const CALENDAR_EVERY = 5 * 60_000

// A day's events, in the browser's time zone; today's are reread every few minutes
export function useCalendar(day: string, today: boolean) {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
  return useQuery({
    queryKey: ['calendar', day, tz],
    queryFn: () => api.calendar(day, tz),
    staleTime: CALENDAR_EVERY,
    refetchInterval: today ? CALENDAR_EVERY : false,
    // keep showing the last day while the next loads
    placeholderData: (prev) => prev,
  })
}
