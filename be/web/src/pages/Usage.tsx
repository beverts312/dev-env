import type { ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import type { UseQueryResult } from '@tanstack/react-query'

import { SectionState } from '@/components/TableSection'
import { Button } from '@/components/ui/button'
import { UsageBar } from '@/components/UsageBar'
import { useClaudeUsage, useCursorUsage } from '@/hooks/queries'
import type { Limit, OnDemand } from '@/lib/api'
import { cn } from '@/lib/utils'

// Your Claude and Cursor plans' usage against their limits
export function Usage() {
  return (
    <div className="space-y-8">
      <Claude />
      <Cursor />
    </div>
  )
}

// Claude's limits, as `claude /usage` reports them
function Claude() {
  const usage = useClaudeUsage()
  const data = usage.data
  const error = usage.error?.message ?? data?.error
  return (
    <Section title="Claude" query={usage} fetchedAt={data?.fetched_at}>
      {data?.plan_note && <p className="text-sm text-muted-foreground">{data.plan_note}</p>}
      {!data?.limits.length ? (
        error || usage.isPending ? (
          <Pending loading={usage.isPending} error={error} />
        ) : (
          // signed in some way /usage has no limits for: show what it said
          <pre className="whitespace-pre-wrap rounded-xl border bg-card p-4 text-xs">{data?.raw || 'no usage'}</pre>
        )
      ) : (
        <>
          <Limits limits={data.limits} />
          {data.details && (
            <pre className="whitespace-pre-wrap rounded-xl border bg-card p-4 text-xs text-muted-foreground">
              {data.details}
            </pre>
          )}
        </>
      )}
    </Section>
  )
}

// Cursor's included usage this billing period and on-demand spend, from Cursor's API
function Cursor() {
  const usage = useCursorUsage()
  const data = usage.data
  const error = usage.error?.message ?? data?.error
  return (
    <Section title="Cursor" query={usage} fetchedAt={data?.fetched_at}>
      {error || usage.isPending ? (
        <Pending loading={usage.isPending} error={error} />
      ) : (
        <>
          {data?.plan && <p className="text-sm text-muted-foreground">{data.plan} plan</p>}
          {data?.limits.length ? <Limits limits={data.limits} /> : null}
          {data?.message && <p className="text-sm text-muted-foreground">{data.message}</p>}
          {data?.on_demand && <p className="text-sm">{onDemandText(data.on_demand)}</p>}
        </>
      )}
    </Section>
  )
}

const dollars = (n: number) => `$${n.toFixed(2)}`

function onDemandText(o: OnDemand) {
  switch (o.kind) {
    case 'fixed':
      return `${dollars(o.used_dollars)} of ${dollars(o.limit_dollars ?? 0)} on-demand`
    case 'unlimited':
      return `${dollars(o.used_dollars)} on-demand, no limit`
    case 'disabled':
      return 'on-demand usage is off'
    default:
      return `${dollars(o.used_dollars)} on-demand`
  }
}

function Section({
  title,
  query,
  fetchedAt,
  children,
}: {
  title: string
  query: UseQueryResult
  fetchedAt?: number
  children: ReactNode
}) {
  return (
    <section aria-label={title} className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <span className="ml-auto text-xs text-muted-foreground">
          {fetchedAt && `updated ${new Date(fetchedAt * 1000).toLocaleTimeString()}`}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
        >
          <RefreshCw className={cn(query.isFetching && 'animate-spin')} />
          refresh
        </Button>
      </div>
      {children}
    </section>
  )
}

function Pending({ loading, error }: { loading: boolean; error?: string | null }) {
  return (
    <div className="rounded-xl border bg-card">
      <SectionState loading={loading} error={error} />
    </div>
  )
}

function Limits({ limits }: { limits: Limit[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {limits.map((l) => (
        <LimitCard key={l.label} limit={l} />
      ))}
    </div>
  )
}

function LimitCard({ limit }: { limit: Limit }) {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{limit.label}</h3>
        <span className="font-mono text-sm">{limit.percent}% used</span>
      </div>
      <UsageBar limit={limit} />
      <p className="text-xs text-muted-foreground">resets {limit.resets}</p>
    </div>
  )
}
