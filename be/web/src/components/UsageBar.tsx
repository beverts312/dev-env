import type { Limit } from '@/lib/api'
import { cn } from '@/lib/utils'

// the fill's color: amber from 75%, red from 90%
function usageColor(percent: number) {
  return percent >= 90 ? 'bg-destructive' : percent >= 75 ? 'bg-amber-500' : 'bg-primary'
}

// A limit's use as a progress bar; thin for inline summaries
export function UsageBar({ limit, thin = false }: { limit: Limit; thin?: boolean }) {
  return (
    <div
      role="progressbar"
      aria-label={limit.label}
      aria-valuenow={limit.percent}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn('overflow-hidden rounded-full bg-muted', thin ? 'h-1.5' : 'h-2')}
    >
      <div
        className={cn('h-full rounded-full transition-[width]', usageColor(limit.percent))}
        style={{ width: `${Math.min(limit.percent, 100)}%` }}
      />
    </div>
  )
}
