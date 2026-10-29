import { AgentPicker } from '@/components/AgentPicker'
import { PrTable } from '@/components/PrTable'
import { useAgent, useMeta } from '@/hooks/queries'
import { TITLES } from '@/lib/pages'

// the review requests, with the agent a review starts; the choice is remembered
export function Reviews() {
  const [agent, setAgent] = useAgent()
  const agents = useMeta().data?.agents ?? ['claude', 'cursor']
  return (
    <>
      <AgentPicker agents={agents} value={agent} onChange={setAgent} />
      <PrTable table="review" title={TITLES.review} />
      <PrTable table="team" title={TITLES.team} />
    </>
  )
}
