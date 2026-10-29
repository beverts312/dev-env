import { useMemo, useState } from 'react'
import { ChevronRight, FolderOpen, FolderPlus } from 'lucide-react'

import { MultiFilter } from '@/components/MultiFilter'
import { SectionState, TableSection } from '@/components/TableSection'
import { WorkspaceDialog } from '@/components/WorkspaceDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAction, useTable } from '@/hooks/queries'
import { api, type Issue } from '@/lib/api'
import { countTree, filterTree, useTreePicks, type ShownIssue } from '@/lib/filters'
import { usePersistent } from '@/lib/store'
import { cn } from '@/lib/utils'

const STATUS_STYLES: Record<string, string> = {
  new: 'bg-muted text-muted-foreground',
  indeterminate: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  done: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
}

// The Jira issues assigned to you, as `jira ls` nests them. Opening an issue opens its workspace,
// or offers to create one or link one
export function IssueTree() {
  const data = useTable('jira')
  const spaces = useTable('workspaces')
  const [picks, setPicks] = useTreePicks()
  const [closed, setClosed] = usePersistent<string[]>('be.tree.closed', [])
  const [creating, setCreating] = useState<Issue | null>(null)
  const open = useAction(api.openWorkspace)

  const issues = data.data?.rows ?? null
  const shown = useMemo(() => filterTree(issues ?? [], picks), [issues, picks])
  const total = issues ? countTree(issues) : 0
  const count = countTree(shown)

  const toggle = (key: string, on: boolean) =>
    setClosed((prev) => (on ? prev.filter((k) => k !== key) : [...prev.filter((k) => k !== key), key]))
  const openIssue = (issue: Issue) => {
    if (issue.workspace) open.mutate([issue.workspace])
    else setCreating(issue)
  }

  const toolbar = issues && (
    <>
      <MultiFilter
        label="projects"
        options={(data.data?.projects ?? []).map((p) => ({ value: p.key, note: p.note }))}
        picked={picks.project}
        onChange={(project) => setPicks({ ...picks, project })}
      />
      <MultiFilter
        label="status"
        options={(data.data?.statuses ?? []).map((value) => ({ value }))}
        picked={picks.status}
        onChange={(status) => setPicks({ ...picks, status })}
      />
    </>
  )

  return (
    <TableSection
      id="jira"
      title="jira issues"
      shown={issues ? count : undefined}
      hidden={total - count}
      onRefresh={data.refresh}
      refreshing={data.refreshing}
      toolbar={toolbar}
    >
      {!issues || !issues.length ? (
        <SectionState
          loading={data.isPending}
          error={data.error?.message ?? (data.data?.error && `jira: ${data.data.error}`)}
          empty="no open issues assigned to you"
        />
      ) : (
        <ul className="py-1 text-sm" role="tree">
          {shown.map((node) => (
            <IssueNode key={node.issue.key} node={node} depth={0} closed={closed} onToggle={toggle} onOpen={openIssue} />
          ))}
        </ul>
      )}
      {creating && (
        <WorkspaceDialog
          key={creating.key}
          issue={creating}
          workspaces={(spaces.data?.rows ?? []).map((w) => w.dir)}
          onClose={() => setCreating(null)}
        />
      )}
    </TableSection>
  )
}

function IssueNode({
  node,
  depth,
  closed,
  onToggle,
  onOpen,
  parentKey,
}: {
  node: ShownIssue
  depth: number
  closed: string[]
  onToggle: (key: string, open: boolean) => void
  onOpen: (issue: Issue) => void
  parentKey?: string
}) {
  const { issue, context, children } = node
  const isOpen = !closed.includes(issue.key)
  const top = depth === 0
  return (
    <li role="treeitem" aria-expanded={children.length ? isOpen : undefined}>
      <div
        data-nav-row
        data-key={issue.key}
        data-parent-key={parentKey}
        onDoubleClick={(e) => {
          // the key links to Jira and the arrow collapses; neither opens a workspace
          if (!(e.target as HTMLElement).closest('a, button')) onOpen(issue)
        }}
        className={cn(
          'group flex min-w-0 items-center gap-2 py-1 pr-3 hover:bg-muted/50',
          context && 'opacity-50',
          !issue.mine && 'text-muted-foreground',
        )}
        style={{ paddingLeft: `${0.75 + depth * 1.25}rem` }}
      >
        {children.length ? (
          <Button
            variant="ghost"
            size="icon-xs"
            data-nav-twist
            aria-expanded={isOpen}
            aria-label={`${isOpen ? 'collapse' : 'expand'} ${issue.key}`}
            onClick={() => onToggle(issue.key, !isOpen)}
          >
            <ChevronRight className={cn('transition-transform', isOpen && 'rotate-90')} />
          </Button>
        ) : (
          <span className="size-6 shrink-0" />
        )}
        <a
          data-nav-link
          href={issue.url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 font-mono text-xs text-primary hover:underline"
        >
          {issue.key}
        </a>
        <span className="shrink-0 text-xs text-muted-foreground">{issue.type}</span>
        <Badge variant="secondary" className={cn('shrink-0', STATUS_STYLES[issue.category])}>
          {issue.status}
        </Badge>
        <span className="truncate">{issue.summary}</span>
        {issue.workspace && (
          <Badge variant="outline" className="shrink-0" title={`workspace ${issue.workspace}`}>
            ws
          </Badge>
        )}
        {!issue.mine ? (
          <span className="shrink-0 text-xs italic">{issue.assignee || 'unassigned'}</span>
        ) : (
          top && issue.parent && <span className="shrink-0 text-xs text-muted-foreground">in {issue.parent}</span>
        )}
        <Button
          variant="ghost"
          size="xs"
          data-nav-primary
          className="ml-auto shrink-0 opacity-0 group-hover:opacity-100 group-data-[selected=true]:opacity-100 focus-visible:opacity-100"
          onClick={() => onOpen(issue)}
        >
          {issue.workspace ? <FolderOpen /> : <FolderPlus />}
          {issue.workspace ? 'open workspace' : 'new workspace'}
        </Button>
      </div>
      {children.length > 0 && isOpen && (
        <ul role="group">
          {children.map((child) => (
            <IssueNode
              key={child.issue.key}
              node={child}
              depth={depth + 1}
              closed={closed}
              onToggle={onToggle}
              onOpen={onOpen}
              parentKey={issue.key}
            />
          ))}
        </ul>
      )}
    </li>
  )
}
