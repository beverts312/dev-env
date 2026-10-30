import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ExternalLink, MailOpen, RefreshCw, Sparkles, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { SectionState } from '@/components/TableSection'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { mailKey, useAction, useMail, useMailActions, useMailThread } from '@/hooks/queries'
import { api, type MailMessage, type MailThread } from '@/lib/api'
import { usePersistent } from '@/lib/store'
import { cn } from '@/lib/utils'

const INBOX = 'in:inbox'
// the read filter, as Gmail search terms added to the query
const READ = { all: '', unread: 'is:unread', read: 'is:read' }
type Read = keyof typeof READ
const ON = 'data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

const when = (ms: string) => {
  const d = new Date(Number(ms))
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

// "Pat Lee <pat@x.com>" as Pat Lee
const sender = (from: string) => from.replace(/\s*<[^>]*>$/, '').replace(/^"|"$/g, '') || from

// Gmail, lightly: a query's threads on the left, the one picked on the right, with claude actions on it.
// Actions open claude in a cmux workspace on the thread; be reads and files mail but never sends it.
export function Mail() {
  const [q, setQ] = usePersistent('be.mail.q', INBOX)
  const [draft, setDraft] = useState(q)
  const [read, setRead] = usePersistent<Read>('be.mail.read', 'all')
  const [picked, setPicked] = useState<string | null>(null)
  const query = [q, READ[read]].filter(Boolean).join(' ')
  const list = useMail(query)
  const trash = useAction(api.trashMail, [mailKey])
  const trashAll = useAction(api.trashMails, [mailKey])
  const threads = list.data?.threads ?? []
  // the threads checked for deleting; only those still listed count
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const anchor = useRef<number | null>(null)
  const ids = threads.filter((t) => checked.has(t.id)).map((t) => t.id)
  const all = threads.length > 0 && ids.length === threads.length

  // shift-click checks or unchecks the run from the last one clicked, as Gmail does
  const check = (i: number, range: boolean) => {
    const on = !checked.has(threads[i].id)
    const from = range && anchor.current !== null ? Math.min(anchor.current, i) : i
    const to = range && anchor.current !== null ? Math.max(anchor.current, i) : i
    const next = new Set(checked)
    threads.slice(from, to + 1).forEach((t) => (on ? next.add(t.id) : next.delete(t.id)))
    setChecked(next)
    anchor.current = i
  }

  const deleteChecked = () =>
    trashAll.mutate([ids], {
      onSuccess: () => {
        if (picked && ids.includes(picked)) setPicked(null)
        setChecked(new Set())
      },
    })

  const search = (e: FormEvent) => {
    e.preventDefault()
    setQ(draft.trim() || INBOX)
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[38rem_minmax(0,1fr)]">
      <section
        data-nav-section
        aria-label="threads"
        className="min-w-0 self-start rounded-r-xl border border-l-0 bg-card text-card-foreground shadow-xs"
      >
        <header className="flex items-center gap-1 p-2">
          <form onSubmit={search} className="flex-1">
            <Input
              data-nav-search
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={INBOX}
              aria-label="search mail"
              className="h-7 text-xs"
            />
          </form>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="refresh mail"
            className="text-muted-foreground"
            onClick={() => void list.refetch()}
            disabled={list.isFetching}
          >
            <RefreshCw className={cn(list.isFetching && 'animate-spin')} />
          </Button>
        </header>
        <div className="flex items-center gap-2 px-3 pb-2">
          <Checkbox
            aria-label="select all"
            checked={all ? true : ids.length ? 'indeterminate' : false}
            onCheckedChange={() => setChecked(all ? new Set() : new Set(threads.map((t) => t.id)))}
            disabled={!threads.length}
          />
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={read}
            onValueChange={(v) => v && setRead(v as Read)}
            aria-label="read or unread"
          >
            {(Object.keys(READ) as Read[]).map((r) => (
              <ToggleGroupItem key={r} value={r} className={ON}>
                {r}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {ids.length > 0 && (
            <>
              <span className="ml-auto text-xs text-muted-foreground">{ids.length} selected</span>
              <Button size="xs" variant="ghost" onClick={() => setChecked(new Set())}>
                clear
              </Button>
              <Button size="xs" variant="destructive" onClick={deleteChecked} disabled={trashAll.isPending}>
                <Trash2 />
                delete {ids.length}
              </Button>
            </>
          )}
        </div>
        <div className="border-t">
          {!list.data || list.data.error || !threads.length ? (
            <SectionState
              loading={!list.data && !list.error}
              error={list.error?.message ?? list.data?.error}
              empty={`no mail for ${query}`}
            />
          ) : (
            <ul className="divide-y">
              {threads.map((t, i) => (
                <ThreadRow
                  key={t.id}
                  thread={t}
                  picked={t.id === picked}
                  checked={checked.has(t.id)}
                  onCheck={(range) => check(i, range)}
                  onPick={() => setPicked(t.id)}
                  onDelete={() => trash.mutate([t.id], { onSuccess: () => t.id === picked && setPicked(null) })}
                />
              ))}
            </ul>
          )}
        </div>
      </section>
      {picked ? (
        <ThreadView id={picked} onDeleted={() => setPicked(null)} />
      ) : (
        <p className="p-4 text-sm text-muted-foreground">pick an email</p>
      )}
    </div>
  )
}

function ThreadRow({
  thread,
  picked,
  checked,
  onCheck,
  onPick,
  onDelete,
}: {
  thread: MailThread
  picked: boolean
  checked: boolean
  onCheck: (range: boolean) => void
  onPick: () => void
  onDelete: () => void
}) {
  const unread = thread.unread
  return (
    <li
      data-nav-row
      data-unread={unread}
      className={cn(
        'group relative flex items-start gap-2 py-2 pr-3 pl-4 text-sm data-[selected=true]:bg-muted/60',
        // unread: a bar on the left edge and full-strength text; read: faded
        unread ? 'bg-primary/5 before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-primary' : 'text-muted-foreground',
        picked && 'bg-muted',
        checked && 'bg-primary/10',
      )}
    >
      <Checkbox
        data-nav-pick
        aria-label={`select ${thread.subject}`}
        checked={checked}
        onClick={(e) => onCheck(e.shiftKey)}
        className="mt-0.5"
      />
      <span
        aria-hidden
        className={cn('mt-1.5 size-2 shrink-0 rounded-full', unread ? 'bg-primary' : 'border border-muted-foreground/40')}
      />
      <button data-nav-primary type="button" onClick={onPick} className="min-w-0 flex-1 text-left">
        <span className="sr-only">{unread ? 'unread' : 'read'}</span>
        <div className="flex items-baseline gap-2">
          <span className={cn('truncate', unread ? 'font-semibold text-foreground' : 'font-normal')}>
            {sender(thread.from)}
          </span>
          {thread.count > 1 && <span className="text-xs text-muted-foreground">{thread.count}</span>}
          <span className={cn('ml-auto shrink-0 text-xs', unread ? 'font-semibold text-primary' : 'text-muted-foreground')}>
            {when(thread.date)}
          </span>
        </div>
        <div className={cn('truncate', unread ? 'font-semibold text-foreground' : 'font-normal')}>{thread.subject}</div>
        <div className="truncate text-xs text-muted-foreground">{thread.snippet}</div>
      </button>
      <div className="flex flex-col">
        {!thread.labels.includes('TRASH') && (
          <Button
            data-nav-action="delete"
            variant="ghost"
            size="icon-sm"
            aria-label={`delete ${thread.subject}`}
            className={HOVER}
            onClick={onDelete}
          >
            <Trash2 />
          </Button>
        )}
        <ClaudeMenu id={thread.id}>
          <Button variant="ghost" size="icon-sm" aria-label={`claude on ${thread.subject}`} className={HOVER}>
            <Sparkles />
          </Button>
        </ClaudeMenu>
      </div>
    </li>
  )
}

// row buttons show on hover or focus, and stay while their menu is open
const HOVER = 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100'

// The mail actions, as a menu opened by children (a button), each opening claude on thread id
function ClaudeMenu({ id, children }: { id: string; children: ReactNode }) {
  const actions = useMailActions()
  const run = useAction((action: string) => api.mailAction(id, { action }))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={run.isPending}>
        {children}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {actions.data?.actions.map((a) => (
          <DropdownMenuItem key={a.key} onSelect={() => run.mutate([a.key])}>
            {a.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ThreadView({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const qc = useQueryClient()
  const thread = useMailThread(id)
  const [prompt, setPrompt] = useState('')
  const trash = useAction(() => api.trashMail(id), [mailKey])
  const unread = useAction(() => api.modifyMail(id, { add: ['UNREAD'] }), [mailKey])
  const run = useAction((ask: { action: string } | { prompt: string }) => api.mailAction(id, ask))
  const data = thread.data
  const isUnread = data?.messages.some((m) => m.unread) ?? false

  // reading a thread marks it read, quietly
  useEffect(() => {
    if (!isUnread) return
    api
      .modifyMail(id, { remove: ['UNREAD'] })
      .then(() => qc.invalidateQueries({ queryKey: [...mailKey, 'list'] }))
      .catch(() => {})
  }, [id, isUnread, qc])

  const ask = (e: FormEvent) => {
    e.preventDefault()
    if (prompt.trim()) run.mutate([{ prompt: prompt.trim() }], { onSuccess: () => setPrompt('') })
  }

  return (
    <section aria-label="email" className="min-w-0 rounded-xl border bg-card text-card-foreground shadow-xs">
      <header className="flex flex-wrap items-center gap-1 p-2">
        <h2 className="mr-auto truncate px-1 text-sm font-semibold">{data?.subject ?? ''}</h2>
        <Button variant="ghost" size="sm" onClick={() => trash.mutate([], { onSuccess: onDeleted })}>
          <Trash2 />
          delete
        </Button>
        <Button variant="ghost" size="sm" onClick={() => unread.mutate([])}>
          <MailOpen />
          mark unread
        </Button>
        <Button variant="ghost" size="icon-sm" asChild>
          <a href={`https://mail.google.com/mail/u/0/#all/${id}`} target="_blank" rel="noreferrer" aria-label="open in Gmail">
            <ExternalLink />
          </a>
        </Button>
        <ClaudeMenu id={id}>
          <Button variant="outline" size="sm">
            <Sparkles />
            claude
          </Button>
        </ClaudeMenu>
      </header>
      <form onSubmit={ask} className="flex gap-1 border-t p-2">
        <Input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="ask claude about this email…"
          aria-label="ask claude"
          className="h-7 text-xs"
        />
        <Button type="submit" size="xs" variant="outline" disabled={!prompt.trim() || run.isPending}>
          ask
        </Button>
      </form>
      <div className="border-t">
        {!data ? (
          <SectionState loading={!thread.error} error={thread.error?.message} />
        ) : (
          <ul className="divide-y">
            {data.messages.map((m) => (
              <Message key={m.id} message={m} />
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function Message({ message: m }: { message: MailMessage }) {
  return (
    <li className="space-y-2 p-3">
      <div className="text-xs text-muted-foreground">
        <div>
          <span className="font-medium text-foreground">{m.from}</span>
          <span className="float-right">{new Date(Number(m.date_ms)).toLocaleString()}</span>
        </div>
        <div>to {m.to}{m.cc && `, cc ${m.cc}`}</div>
      </div>
      {m.html ? (
        // email HTML is untrusted: no scripts, no same origin; links open in a new tab
        <iframe
          title={`message from ${sender(m.from)}`}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          srcDoc={`<base target="_blank">${m.html}`}
          className="h-[60vh] w-full resize-y rounded-md border bg-white"
        />
      ) : (
        <pre className="text-sm whitespace-pre-wrap font-sans">{m.text}</pre>
      )}
    </li>
  )
}
