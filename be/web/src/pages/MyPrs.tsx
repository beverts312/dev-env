import { PrTable } from '@/components/PrTable'
import { TITLES } from '@/lib/pages'

export function MyPrs() {
  return <PrTable table="mine" title={TITLES.mine} />
}
