import { useState } from 'react'
import { Code, FolderOpen, MessagesSquare, Trash2 } from 'lucide-react'

import { ConfirmButton } from '@/components/ConfirmButton'
import { SessionsDialog } from '@/components/SessionsDialog'
import { SectionState, TableSection } from '@/components/TableSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAction, useTable } from '@/hooks/queries'
import { api } from '@/lib/api'

// The workspaces in ws.dir; clicking one opens it, as `ws open` does; sessions lists its claude sessions
export function WorkspaceTable() {
  const data = useTable('workspaces')
  const open = useAction(api.openWorkspace)
  const vscode = useAction(api.openVscode)
  const remove = useAction(api.deleteWorkspace, ['workspaces', 'jira'])
  const [sessionsFor, setSessionsFor] = useState<string | null>(null)
  const rows = data.data?.rows ?? null
  return (
    <TableSection
      id="workspaces"
      title="workspaces"
      shown={rows?.length}
      onRefresh={data.refresh}
      refreshing={data.refreshing}
    >
      {!rows || !rows.length ? (
        <SectionState
          loading={data.isPending}
          error={data.error?.message ?? (data.data?.error && `workspaces: ${data.data.error}`)}
          empty="no workspaces"
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>name</TableHead>
              <TableHead>issue</TableHead>
              <TableHead>description</TableHead>
              <TableHead>repos</TableHead>
              <TableHead>extra</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((w) => (
              <TableRow
                key={w.dir}
                data-nav-row
                className="cursor-pointer"
                onClick={(e) => {
                  if (!(e.target as HTMLElement).closest('button')) open.mutate([w.dir])
                }}
              >
                <TableCell className="font-medium">{w.dir}</TableCell>
                <TableCell className="max-w-56 truncate text-muted-foreground">
                  {w.issues?.length ? <span className="mr-1 font-mono text-xs">{w.issues.join(', ')}</span> : null}
                  {w.issue_name}
                </TableCell>
                <TableCell className="max-w-72 truncate text-muted-foreground">{w.description}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {w.repos.map((r) => (
                      <Badge key={r} variant="secondary">
                        {r}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{w.extra_dirs.join(', ')}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button size="xs" variant="outline" className="mr-1" onClick={() => vscode.mutate([w.dir])}>
                    <Code />
                    vscode
                  </Button>
                  <Button size="xs" variant="outline" className="mr-1" onClick={() => setSessionsFor(w.dir)}>
                    <MessagesSquare />
                    sessions
                  </Button>
                  <Button size="xs" variant="outline" data-nav-primary onClick={() => open.mutate([w.dir])}>
                    <FolderOpen />
                    open
                  </Button>
                  <ConfirmButton
                    size="xs"
                    variant="ghost"
                    className="ml-1 text-destructive"
                    disabled={remove.isPending}
                    aria-label={`delete ${w.dir}`}
                    title={`Delete workspace ${w.dir}?`}
                    description={
                      w.repos.length
                        ? `This deletes the folder, its clones of ${w.repos.join(', ')} with any unpushed work, its saved cmux layout, and its claude sessions.`
                        : 'This deletes the folder, its saved cmux layout, and its claude sessions.'
                    }
                    confirm="delete"
                    onConfirm={() => remove.mutate([w.dir])}
                  >
                    <Trash2 />
                  </ConfirmButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {sessionsFor && <SessionsDialog key={sessionsFor} workspace={sessionsFor} onClose={() => setSessionsFor(null)} />}
    </TableSection>
  )
}
