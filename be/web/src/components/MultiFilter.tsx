import { ChevronDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

// A dropdown of checkboxes; none checked shows everything
export function MultiFilter({
  label,
  options,
  picked,
  onChange,
}: {
  label: string
  options: { value: string; note?: string }[]
  picked: string[]
  onChange: (picked: string[]) => void
}) {
  const toggle = (value: string, on: boolean) =>
    onChange(on ? [...picked, value] : picked.filter((x) => x !== value))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={picked.length ? 'secondary' : 'outline'} size="xs" className="max-w-64">
          <span className="text-muted-foreground">{label}</span>
          <span className="truncate">{picked.length ? picked.join(', ') : 'all'}</span>
          <ChevronDown />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        {options.map((o) => (
          <DropdownMenuCheckboxItem
            key={o.value}
            checked={picked.includes(o.value)}
            onCheckedChange={(on) => toggle(o.value, on)}
            onSelect={(e) => e.preventDefault()}
          >
            {o.value}
            {o.note && <span className="ml-auto pl-3 text-xs text-muted-foreground">{o.note}</span>}
          </DropdownMenuCheckboxItem>
        ))}
        {!options.length && <DropdownMenuItem disabled>nothing to filter</DropdownMenuItem>}
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={!picked.length} onSelect={() => onChange([])}>
          show all
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
