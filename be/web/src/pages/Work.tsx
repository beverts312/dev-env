import { IssueTree } from '@/components/IssueTree'
import { StarredTable } from '@/components/PrTable'
import { TITLES } from '@/lib/pages'

export function Work() {
  return (
    <>
      <IssueTree />
      <StarredTable title={TITLES.starred} />
    </>
  )
}
