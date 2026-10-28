import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api, type Done, type TableId } from '@/lib/api'
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
