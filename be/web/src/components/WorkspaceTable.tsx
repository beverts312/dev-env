import { FolderOpen } from 'lucide-react'

import { SectionState, TableSection } from '@/components/TableSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAction, useTable } from '@/hooks/queries'
import { api } from '@/lib/api'

// The workspaces in ws.dir; clicking one opens it, as `ws open` does
export function WorkspaceTable() {
  const data = useTable('workspaces')
  const open = useAction(api.openWorkspace)
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
                <TableCell className="text-right">
                  <Button size="xs" variant="outline" data-nav-primary onClick={() => open.mutate([w.dir])}>
                    <FolderOpen />
                    open
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </TableSection>
  )
}
