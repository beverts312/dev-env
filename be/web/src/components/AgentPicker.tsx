import { Check, Sparkles, SquareTerminal, type LucideIcon } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { UsageBar } from '@/components/UsageBar'
import { useClaudeUsage, useCursorUsage } from '@/hooks/queries'
import type { Limit } from '@/lib/api'
import { cn } from '@/lib/utils'

const ICONS: Record<string, LucideIcon> = { claude: Sparkles, cursor: SquareTerminal }

// /usage's labels, shortened to fit a card: "Current week (all models)" is "week (all models)"
const short = (label: string) => label.replace(/^Current /, '').toLowerCase()

// The agent a review starts, as a card per agent with its plan's usage now
export function AgentPicker({
  agents,
  value,
  onChange,
}: {
  agents: string[]
  value: string
  onChange: (agent: string) => void
}) {
  const claude = useClaudeUsage()
  const cursor = useCursorUsage()
  const usage: Record<string, { limits?: Limit[]; error?: string | null; loading: boolean }> = {
    claude: { limits: claude.data?.limits, error: claude.error?.message ?? claude.data?.error, loading: claude.isPending },
    cursor: { limits: cursor.data?.limits, error: cursor.error?.message ?? cursor.data?.error, loading: cursor.isPending },
  }
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold" id="agent-label">
          review agent
        </h2>
        <Link to="/usage" className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline">
          usage details
        </Link>
      </div>
      <RadioGroupPrimitive.Root
        value={value}
        onValueChange={onChange}
        aria-labelledby="agent-label"
        className="grid gap-3 sm:grid-cols-2"
      >
        {agents.map((a) => {
          const Icon = ICONS[a] ?? SquareTerminal
          const u = usage[a]
          return (
            <RadioGroupPrimitive.Item
              key={a}
              value={a}
              aria-label={a}
              className={cn(
                'group flex flex-col gap-3 rounded-xl border bg-card p-3 text-left transition-colors outline-none',
                'hover:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/50',
                'data-[state=checked]:border-primary data-[state=checked]:bg-primary/5 data-[state=checked]:ring-1 data-[state=checked]:ring-primary',
              )}
            >
              <div className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg bg-muted text-muted-foreground group-data-[state=checked]:bg-primary group-data-[state=checked]:text-primary-foreground">
                  <Icon className="size-4" />
                </span>
                <span className="text-sm font-medium capitalize">{a}</span>
                <Check className="ml-auto size-4 text-primary opacity-0 group-data-[state=checked]:opacity-100" />
              </div>
              {u && <AgentUsage {...u} />}
            </RadioGroupPrimitive.Item>
          )
        })}
      </RadioGroupPrimitive.Root>
    </div>
  )
}

function AgentUsage({ limits, error, loading }: { limits?: Limit[]; error?: string | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    )
  }
  if (error) return <p className="line-clamp-2 text-xs text-destructive">{error}</p>
  if (!limits?.length) return <p className="text-xs text-muted-foreground">no usage limits reported</p>
  return (
    <div className="space-y-2">
      {limits.map((l) => (
        <div key={l.label} className="space-y-1" title={`resets ${l.resets}`}>
          <div className="flex items-baseline gap-2 text-xs">
            <span className="text-muted-foreground">{short(l.label)}</span>
            <span className="ml-auto font-mono">{l.percent}%</span>
          </div>
          <UsageBar limit={l} thin />
        </div>
      ))}
    </div>
  )
}
