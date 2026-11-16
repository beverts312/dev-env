import { ConfirmButton } from '@/components/ConfirmButton'
import { Button } from '@/components/ui/button'
import { ACTION_LABELS, type BulkAction, type MineAction, type Pr } from '@/lib/api'

const MINE_ACTIONS = Object.keys(ACTION_LABELS) as MineAction[]
const LABELS: Record<BulkAction, string> = { ...ACTION_LABELS, approve: 'approve' }
// these act for good, or in your name, so they ask first
const CONFIRMED: BulkAction[] = ['merge', 'approve']

// Acts on the checked PRs: your PRs' actions, or approving review requests. Each button counts
// the checked PRs it applies to, and is disabled when there are none
export function BulkBar({
  picked,
  mine,
  onRun,
}: {
  picked: Pr[]
  mine: boolean
  onRun: (action: BulkAction) => void
}) {
  const actions: BulkAction[] = mine ? MINE_ACTIONS : ['approve']
  // any review request can be approved; your PRs say what they offer
  const count = (action: BulkAction) => (mine ? picked.filter((p) => p.actions?.includes(action as MineAction)).length : picked.length)
  return (
    <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs">
      <span className="text-muted-foreground" data-testid="picked-count">
        {picked.length} selected
      </span>
      {actions.map((action) => {
        const n = count(action)
        const text = `${LABELS[action]} (${n})`
        return CONFIRMED.includes(action) ? (
          <ConfirmButton
            key={action}
            size="xs"
            variant="outline"
            disabled={!n}
            title={`${LABELS[action][0].toUpperCase()}${LABELS[action].slice(1)} ${n} PR${n === 1 ? '' : 's'}?`}
            confirm={LABELS[action]}
            onConfirm={() => onRun(action)}
          >
            {text}
          </ConfirmButton>
        ) : (
          <Button key={action} size="xs" variant="outline" disabled={!n} onClick={() => onRun(action)}>
            {text}
          </Button>
        )
      })}
    </div>
  )
}
