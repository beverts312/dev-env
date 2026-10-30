import { useCallback, useState } from 'react'
import { Keyboard, Moon, NotebookPen, Settings2, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { NavLink, Outlet, useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Kbd } from '@/components/ui/kbd'
import { Separator } from '@/components/ui/separator'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { useAction, useTable } from '@/hooks/queries'
import { useKeyboardNav } from '@/hooks/useKeyboardNav'
import { api, type PrTableId } from '@/lib/api'
import { countTree, filterTree, prShown, usePrFilters, useTreePicks } from '@/lib/filters'
import { KEYS, PAGES, type CountId } from '@/lib/pages'
import { usePersistent } from '@/lib/store'
import { cn } from '@/lib/utils'

export function Layout() {
  const [open, setOpen] = usePersistent('be.sidebar', true)
  const [help, setHelp] = useState(false)
  const { pathname } = useLocation()
  useKeyboardNav(useCallback(() => setHelp(true), []))
  const page = PAGES.find((p) => p.path === pathname)
  const notes = useAction(api.openNotes)
  const configs = useAction(api.openConfigs)

  return (
    <SidebarProvider open={open} onOpenChange={setOpen}>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <NavLink to="/" aria-label="home" className="flex items-center gap-2 px-1 py-1">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
              be
            </div>
            <span className="truncate text-sm font-medium group-data-[collapsible=icon]:hidden">dev env</span>
          </NavLink>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {PAGES.filter((p) => p.path !== '/' && p.tables.length).map((p) => (
                  <NavItem key={p.path} page={p} active={pathname === p.path} />
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            {PAGES.filter((p) => !p.tables.length).map((p) => (
              <NavItem key={p.path} page={p} active={pathname === p.path} />
            ))}
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-12 items-center gap-2 border-b bg-background/80 px-3 backdrop-blur">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <h1 className="text-sm font-medium">{page?.label ?? 'not found'}</h1>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => notes.mutate([])} className="text-muted-foreground">
              <NotebookPen />
              notes
            </Button>
            <Button variant="ghost" size="sm" onClick={() => configs.mutate([])} className="text-muted-foreground">
              <Settings2 />
              configs
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setHelp(true)} className="text-muted-foreground">
              <Keyboard />
              keys
            </Button>
            <ThemeToggle />
          </div>
        </header>
        {/* home is wider, for its calendar pane */}
        <div className={cn('mx-auto w-full space-y-4 p-4', pathname === '/' ? 'max-w-[96rem]' : 'max-w-7xl')}>
          <Outlet />
        </div>
      </SidebarInset>
      <Dialog open={help} onOpenChange={setHelp}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Keys</DialogTitle>
          </DialogHeader>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {KEYS.map(([keys, what]) => (
              <div key={keys} className="contents">
                <dt>
                  <Kbd>{keys}</Kbd>
                </dt>
                <dd className="text-muted-foreground">{what}</dd>
              </div>
            ))}
          </dl>
        </DialogContent>
      </Dialog>
    </SidebarProvider>
  )
}

function NavItem({ page, active }: { page: (typeof PAGES)[number]; active: boolean }) {
  const Icon = page.icon
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={active} tooltip={page.label}>
        <NavLink to={page.path}>
          <Icon />
          <span>{page.label}</span>
        </NavLink>
      </SidebarMenuButton>
      {page.tables.length > 0 && <PageCount tables={page.tables} />}
    </SidebarMenuItem>
  )
}

// each page's badge counts the rows its filters show, across its tables
function PageCount({ tables }: { tables: CountId[] }) {
  const n = useShownCount(tables)
  return n ? <SidebarMenuBadge className="tabular-nums">{n}</SidebarMenuBadge> : null
}

function useShownCount(tables: CountId[]) {
  const review = useTable('review').data?.rows
  const team = useTable('team').data?.rows
  const mine = useTable('mine').data?.rows
  const jira = useTable('jira').data?.rows
  const workspaces = useTable('workspaces').data?.rows
  const [reviewFilters] = usePrFilters('review')
  const [teamFilters] = usePrFilters('team')
  const [mineFilters] = usePrFilters('mine')
  const [picks] = useTreePicks()
  const prs = (rows: typeof review, filters: typeof reviewFilters, table: PrTableId) =>
    (rows ?? []).filter((p) => prShown(p, filters, table === 'mine')).length
  const counts: Record<CountId, () => number> = {
    review: () => prs(review, reviewFilters, 'review'),
    team: () => prs(team, teamFilters, 'team'),
    mine: () => prs(mine, mineFilters, 'mine'),
    jira: () => (jira ? countTree(filterTree(jira, picks)) : 0),
    workspaces: () => workspaces?.length ?? 0,
  }
  return tables.reduce((n, t) => n + counts[t](), 0)
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme !== 'light'
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={dark ? 'switch to light' : 'switch to dark'}
      onClick={() => setTheme(dark ? 'light' : 'dark')}
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}
