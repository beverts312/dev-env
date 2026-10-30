import { CalendarPane } from '@/components/CalendarPane'
import { IssueTree } from '@/components/IssueTree'
import { StarredTable } from '@/components/PrTable'
import { TITLES } from '@/lib/pages'

export function Home() {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        <StarredTable title={TITLES.starred} />
        <IssueTree />
      </div>
      <aside className="lg:sticky lg:top-16 lg:max-h-[calc(100svh-5rem)] lg:self-start lg:overflow-auto">
        <CalendarPane />
      </aside>
    </div>
  )
}
