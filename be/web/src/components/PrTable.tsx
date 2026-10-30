import { useMemo, useState } from 'react'
import { ExternalLink, Search, Star } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { BulkBar } from '@/components/BulkBar'
import { ConfirmButton } from '@/components/ConfirmButton'
import { SectionState, TableSection } from '@/components/TableSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { tableKey, useAction, useAgent, useStarred, useStarredTable, useTable } from '@/hooks/queries'
import { ACTION_LABELS, api, prName, type MineAction, type Pr, type PrTableId, type PrViewId } from '@/lib/api'
import { ALL, CHECKS, DRAFT, filtersOn, prShown, toggleAll, usePrFilters } from '@/lib/filters'
import { cn } from '@/lib/utils'

const CHECK_STYLES: Record<string, string> = {
  pass: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  fail: 'bg-red-500/15 text-red-600 dark:text-red-400',
  pending: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
}

// What a PR table draws from: the server's table, or the starred PRs
type PrSource = {
  rows: Pr[] | null
  error: string | null
  empty?: string
  loading?: boolean
  notLoaded?: boolean
  refresh: () => void
  refreshing: boolean
}

// A `pr ls` table: review requests, team review requests, or your PRs, which can also be marked
// ready, set to auto-merge, or merged, one at a time or checked and done in bulk
export function PrTable({ table, title }: { table: PrTableId; title: string }) {
  const data = useTable(table)
  const rows = data.data?.rows ?? null
  const source: PrSource = {
    rows,
    error: data.error?.message ?? (data.data?.error ? `github: ${data.data.error}` : null),
    empty: data.data?.empty,
    loading: data.isPending,
    notLoaded: rows === null,
    refresh: data.refresh,
    refreshing: data.refreshing,
  }
  return <PrTableView table={table} title={title} data={source} />
}

// The PRs starred from your PRs or reviews, until they're merged
export function StarredTable({ title }: { title: string }) {
  const data = useStarredTable()
  const empty = 'no starred PRs; star one from your PRs or reviews'
  return <PrTableView table="starred" title={title} data={{ ...data, empty }} />
}

function PrTableView({ table, title, data }: { table: PrViewId; title: string; data: PrSource }) {
  const mine = table === 'mine'
  const qc = useQueryClient()
  const [filters, setFilters] = usePrFilters(table)
  const [agent] = useAgent()
  const star = useStarred()
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const review = useAction((p: Pr) => api.review(p.repo, p.number, agent))
  const act = useAction((action: MineAction, p: Pr) => api.mineAction(action, p.repo, p.number), ['mine'])

  const rows = data.rows
  const shown = useMemo(() => (rows ?? []).filter((p) => prShown(p, filters, mine)), [rows, filters, mine])
  // a hidden row is never acted on in bulk
  const pickedShown = shown.filter((p) => picked.has(prName(p)))
  const setPick = (p: Pr, on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (on) next.add(prName(p))
      else next.delete(prName(p))
      return next
    })

  const runBulk = async (action: MineAction) => {
    try {
      // only the PRs the button counted
      const prs = pickedShown.filter((p) => p.actions?.includes(action)).map(prName)
      const done = await api.bulk(action, prs)
      const failed = done.results.filter((r) => !r.ok)
      const lines = done.results.map((r) => r.message)
      if (failed.length) toast.warning(`${failed.length} of ${lines.length} didn't go`, { description: lines.join('\n') })
      else toast.success(lines.join('\n'))
      setPicked(new Set())
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      await qc.invalidateQueries({ queryKey: tableKey('mine') })
    }
  }

  const toolbar = (
    <>
      <FilterSelect label="checks" value={filters.checks} options={CHECKS} onChange={(checks) => setFilters({ ...filters, checks })} />
      <FilterSelect label="draft" value={filters.draft} options={DRAFT} onChange={(draft) => setFilters({ ...filters, draft })} />
      {!mine && (
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox checked={filters.renovate} onCheckedChange={(on) => setFilters({ ...filters, renovate: on === true })} />
          not by renovate
        </label>
      )}
      <Button variant="ghost" size="xs" data-nav-allfilters onClick={() => setFilters(toggleAll(filters))}>
        {filtersOn(filters) ? 'show all' : 'default filters'}
      </Button>
      <div className="relative ml-auto">
        <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          data-nav-search
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          placeholder="repo or title"
          aria-label="search repo or title"
          className="h-7 w-48 pl-7 text-xs"
        />
      </div>
    </>
  )

  // a column every shown row agrees on says nothing
  const showChecks = filters.checks === ALL
  const showDraft = filters.draft === ALL

  return (
    <TableSection
      id={table}
      title={title}
      defaultCollapsed={table === 'starred'}
      shown={rows ? shown.length : undefined}
      hidden={rows ? rows.length - shown.length : 0}
      onRefresh={data.refresh}
      refreshing={data.refreshing}
      toolbar={toolbar}
    >
      {mine && rows && rows.length > 0 && (
        <BulkBar picked={pickedShown} onRun={runBulk} />
      )}
      {!rows || !rows.length ? (
        <SectionState
          loading={data.loading}
          error={data.error}
          notLoaded={data.notLoaded}
          empty={data.empty}
          onLoad={data.refresh}
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              {mine && (
                <TableHead className="w-8">
                  <Checkbox
                    aria-label="select all shown"
                    checked={shown.length > 0 && pickedShown.length === shown.length}
                    onCheckedChange={(on) => setPicked(new Set(on === true ? shown.map(prName) : []))}
                  />
                </TableHead>
              )}
              <TableHead className="w-8" />
              <TableHead>PR</TableHead>
              <TableHead>repo</TableHead>
              {!mine && <TableHead>author</TableHead>}
              {showChecks && <TableHead>checks</TableHead>}
              <TableHead className="text-right">approvals</TableHead>
              {showDraft && <TableHead>draft</TableHead>}
              <TableHead>title</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((p) => (
              <TableRow key={prName(p)} data-nav-row data-pr={prName(p)}>
                {mine && (
                  <TableCell>
                    <Checkbox
                      data-nav-pick
                      aria-label={`select ${prName(p)}`}
                      checked={picked.has(prName(p))}
                      onCheckedChange={(on) => setPick(p, on === true)}
                    />
                  </TableCell>
                )}
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    data-nav-star
                    aria-label={`${star.isStarred(p) ? 'unstar' : 'star'} ${prName(p)}`}
                    aria-pressed={star.isStarred(p)}
                    onClick={() => star.toggle(p)}
                  >
                    <Star className={cn(star.isStarred(p) ? 'fill-amber-400 text-amber-500' : 'text-muted-foreground')} />
                  </Button>
                </TableCell>
                <TableCell>
                  <a
                    data-nav-link
                    href={p.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-mono text-primary hover:underline"
                  >
                    #{p.number}
                    <ExternalLink className="size-3 opacity-60" />
                  </a>
                </TableCell>
                <TableCell className="text-muted-foreground">{p.repo}</TableCell>
                {!mine && <TableCell className="text-muted-foreground">{p.author}</TableCell>}
                {showChecks && (
                  <TableCell>
                    <Badge variant="secondary" className={cn(CHECK_STYLES[p.checks])}>
                      {p.checks}
                    </Badge>
                  </TableCell>
                )}
                <TableCell className="text-right tabular-nums">{p.approvals}</TableCell>
                {showDraft && <TableCell className="text-muted-foreground">{p.draft ? 'yes' : 'no'}</TableCell>}
                <TableCell className="max-w-md truncate" title={p.title}>
                  {p.title}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button size="xs" variant="outline" data-nav-primary onClick={() => review.mutate([p])}>
                      review
                    </Button>
                    {p.actions?.map((action) =>
                      action === 'merge' ? (
                        <ConfirmButton
                          key={action}
                          size="xs"
                          title={`Merge ${prName(p)}?`}
                          description={p.title}
                          confirm="merge"
                          onConfirm={() => act.mutate([action, p])}
                        >
                          merge
                        </ConfirmButton>
                      ) : (
                        <Button
                          key={action}
                          size="xs"
                          variant="secondary"
                          data-nav-action={action}
                          onClick={() => act.mutate([action, p])}
                        >
                          {ACTION_LABELS[action]}
                        </Button>
                      ),
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </TableSection>
  )
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {label}
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger size="sm" className="h-7 text-xs" aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[ALL, ...options].map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}
