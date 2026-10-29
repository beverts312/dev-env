import { ConfirmButton } from '@/components/ConfirmButton'
import { Button } from '@/components/ui/button'
import { ACTION_LABELS, type MineAction, type Pr } from '@/lib/api'

const ACTIONS = Object.entries(ACTION_LABELS) as [MineAction, string][]

// Acts on your checked PRs; each button counts the checked PRs it applies to, and is disabled
// when there are none
export function BulkBar({ picked, onRun }: { picked: Pr[]; onRun: (action: MineAction) => void }) {
  const count = (action: MineAction) => picked.filter((p) => p.actions?.includes(action)).length
  return (
    <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs">
      <span className="text-muted-foreground" data-testid="picked-count">
        {picked.length} selected
      </span>
      {ACTIONS.map(([action, label]) => {
        const n = count(action)
        const text = `${label} (${n})`
        return action === 'merge' ? (
          <ConfirmButton
            key={action}
            size="xs"
            variant="outline"
            disabled={!n}
            title={`Merge ${n} PR${n === 1 ? '' : 's'}?`}
            confirm="merge"
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
