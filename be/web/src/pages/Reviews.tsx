import { PrTable } from '@/components/PrTable'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useAgent, useMeta } from '@/hooks/queries'
import { TITLES } from '@/lib/pages'

// the review requests, with the agent a review starts; the choice is remembered
export function Reviews() {
  const [agent, setAgent] = useAgent()
  const agents = useMeta().data?.agents ?? ['claude', 'cursor']
  return (
    <>
      <div className="flex items-center gap-3 text-sm">
        <span className="text-muted-foreground" id="agent-label">
          review agent
        </span>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={agent}
          onValueChange={(v) => v && setAgent(v)}
          aria-labelledby="agent-label"
        >
          {agents.map((a) => (
            <ToggleGroupItem
              key={a}
              value={a}
              className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
            >
              {a}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <PrTable table="review" title={TITLES.review} />
      <PrTable table="team" title={TITLES.team} />
    </>
  )
}
