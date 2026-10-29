import { useState, type FormEvent } from 'react'
import { ExternalLink, Plus } from 'lucide-react'

import { MultiFilter } from '@/components/MultiFilter'
import { SectionState, TableSection } from '@/components/TableSection'
import { TodoDialog } from '@/components/TodoDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { todosKey, useAction, useTodos } from '@/hooks/queries'
import { api, type Todo } from '@/lib/api'
import { usePersistent } from '@/lib/store'
import { cn } from '@/lib/utils'

const PRIORITY: Record<string, 'destructive' | 'secondary' | 'outline'> = {
  high: 'destructive',
  med: 'secondary',
  low: 'outline',
}

// The todos in todo.dir, as `todo ls` orders them: check one off, add one by title, or click one to
// edit its fields and notes
export function TodoTable() {
  const [showDone, setShowDone] = usePersistent('be.todos.done', false)
  const [tags, setTags] = usePersistent<string[]>('be.todos.tags', [])
  const [title, setTitle] = useState('')
  const [editing, setEditing] = useState<Todo | null>(null)
  const data = useTodos(showDone)
  const add = useAction(api.addTodo, [todosKey])
  const done = useAction(api.doneTodo, [todosKey])
  const reopen = useAction(api.reopenTodo, [todosKey])
  const all = data.data?.rows ?? null
  const rows = all?.filter((t) => !tags.length || tags.some((tag) => t.tags.includes(tag))) ?? null
  const options = [...new Set(all?.flatMap((t) => t.tags))].sort().map((value) => ({ value }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (title.trim()) add.mutate([{ title: title.trim() }], { onSuccess: () => setTitle('') })
  }

  const toolbar = (
    <>
      <form onSubmit={submit} className="flex items-center gap-1">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="new todo"
          aria-label="new todo"
          className="h-7 w-64 text-xs"
        />
        <Button type="submit" size="xs" variant="outline" disabled={!title.trim() || add.isPending}>
          <Plus />
          add
        </Button>
      </form>
      {options.length > 0 && <MultiFilter label="tags" options={options} picked={tags} onChange={setTags} />}
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Checkbox checked={showDone} onCheckedChange={(on) => setShowDone(on === true)} />
        show done
      </label>
      {data.data?.dir && <span className="ml-auto font-mono text-xs text-muted-foreground">{data.data.dir}</span>}
    </>
  )

  return (
    <TableSection
      id="todos"
      title="todos"
      shown={rows?.length}
      hidden={(all?.length ?? 0) - (rows?.length ?? 0)}
      onRefresh={() => void data.refetch()}
      refreshing={data.isFetching}
      toolbar={toolbar}
    >
      {!rows || !rows.length ? (
        <SectionState
          loading={data.isPending}
          error={data.error?.message ?? (data.data?.error && `todos: ${data.data.error}`)}
          empty="no todos"
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>title</TableHead>
              <TableHead>due</TableHead>
              <TableHead>priority</TableHead>
              <TableHead>jira</TableHead>
              <TableHead>tags</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((t) => {
              const isDone = t.status === 'done'
              return (
                <TableRow
                  key={t.id}
                  data-nav-row
                  className={cn('cursor-pointer', isDone && 'text-muted-foreground')}
                  onClick={(e) => {
                    if (!(e.target as HTMLElement).closest('button, a, [role="checkbox"]')) setEditing(t)
                  }}
                >
                  <TableCell>
                    <Checkbox
                      data-nav-pick
                      checked={isDone}
                      aria-label={`${isDone ? 'reopen' : 'check off'} ${t.title}`}
                      onCheckedChange={(on) => (on ? done : reopen).mutate([t.id])}
                    />
                  </TableCell>
                  <TableCell className="max-w-96">
                    <button
                      type="button"
                      data-nav-primary
                      className={cn('truncate text-left font-medium', isDone && 'line-through')}
                      onClick={() => setEditing(t)}
                    >
                      {t.title}
                    </button>
                    {t.notes && <div className="truncate text-xs text-muted-foreground">{t.notes.split('\n')[0]}</div>}
                  </TableCell>
                  <TableCell className={cn('font-mono text-xs whitespace-nowrap', t.overdue && 'font-semibold text-destructive')}>
                    {t.due}
                  </TableCell>
                  <TableCell>{t.priority && <Badge variant={PRIORITY[t.priority]}>{t.priority}</Badge>}</TableCell>
                  <TableCell>
                    {t.jira &&
                      (t.url ? (
                        <a
                          data-nav-link
                          href={t.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
                        >
                          {t.jira}
                          <ExternalLink className="size-3 opacity-60" />
                        </a>
                      ) : (
                        <span className="font-mono text-xs">{t.jira}</span>
                      ))}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {t.tags.map((tag) => (
                        <Badge key={tag} variant="secondary">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
      {editing && <TodoDialog key={editing.id} todo={editing} onClose={() => setEditing(null)} />}
    </TableSection>
  )
}
