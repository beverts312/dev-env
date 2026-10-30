import type { ReactNode } from 'react'
import { ChevronDown, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePersistent } from '@/lib/store'
import { cn } from '@/lib/utils'

// A titled card holding one table, with its collapse toggle (remembered, else defaultCollapsed), shown and hidden
// counts, actions and refresh button, and filters. The keyboard moves between the rows of a page's sections.
export function TableSection({
  id,
  title,
  shown,
  hidden = 0,
  onRefresh,
  refreshing = false,
  actions,
  toolbar,
  defaultCollapsed = false,
  children,
}: {
  id: string
  title: string
  shown?: number
  hidden?: number
  onRefresh?: () => void
  refreshing?: boolean
  actions?: ReactNode
  toolbar?: ReactNode
  defaultCollapsed?: boolean
  children: ReactNode
}) {
  const [collapsed, setCollapsed] = usePersistent(`be.collapsed.${id}`, defaultCollapsed)
  return (
    <section
      data-nav-section
      data-table={id}
      data-collapsed={collapsed}
      className="rounded-xl border bg-card text-card-foreground shadow-xs"
    >
      <header className="flex items-center gap-2 px-3 py-2.5">
        <Button
          variant="ghost"
          size="icon-sm"
          data-nav-collapse
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? 'expand' : 'collapse'} ${title}`}
          onClick={() => setCollapsed(!collapsed)}
        >
          <ChevronDown className={cn('transition-transform', collapsed && '-rotate-90')} />
        </Button>
        <h2 className="text-sm font-semibold">{title}</h2>
        {shown !== undefined && <Badge variant="secondary">{shown}</Badge>}
        {hidden > 0 && <span className="text-xs text-muted-foreground">{hidden} hidden</span>}
        {(actions || onRefresh) && (
          <div className="ml-auto flex items-center gap-1">
            {actions}
            {onRefresh && (
              <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={cn(refreshing && 'animate-spin')} />
                refresh
              </Button>
            )}
          </div>
        )}
      </header>
      {!collapsed && (
        <>
          {toolbar && <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2">{toolbar}</div>}
          <div className="border-t">{children}</div>
        </>
      )}
    </section>
  )
}

// What a section shows in place of rows: loading, an error, not loaded yet, or empty
export function SectionState({
  loading,
  error,
  notLoaded,
  empty,
  onLoad,
}: {
  loading?: boolean
  error?: string | null
  notLoaded?: boolean
  empty?: string
  onLoad?: () => void
}) {
  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[0, 1, 2].map((n) => (
          <Skeleton key={n} className="h-6 w-full" />
        ))}
      </div>
    )
  }
  if (error) return <p className="p-4 text-sm text-destructive">{error}</p>
  if (notLoaded) {
    return (
      <div className="flex items-center gap-3 p-4 text-sm text-muted-foreground">
        not loaded yet
        {onLoad && (
          <Button size="sm" variant="outline" onClick={onLoad}>
            load
          </Button>
        )}
      </div>
    )
  }
  return <p className="p-4 text-sm text-muted-foreground">{empty}</p>
}
