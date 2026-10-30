import { Play, Trash2 } from 'lucide-react'

import { ConfirmButton } from '@/components/ConfirmButton'
import { SectionState } from '@/components/TableSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { sessionsKey, useAction, useSessions } from '@/hooks/queries'
import { api } from '@/lib/api'

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

// The claude sessions run in a workspace: resume one in a new pane of its cmux workspace, or delete
// its transcript. Mount it with a key per workspace, so each opens fresh.
export function SessionsDialog({ workspace, onClose }: { workspace: string; onClose: () => void }) {
  const data = useSessions(workspace)
  const resume = useAction(api.resumeSession)
  const remove = useAction(api.deleteSession, [sessionsKey(workspace)])
  const sessions = data.data?.sessions
  const busy = resume.isPending || remove.isPending

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Claude sessions</DialogTitle>
          <DialogDescription className="font-mono text-xs">{workspace}</DialogDescription>
        </DialogHeader>
        {!sessions || !sessions.length ? (
          <SectionState loading={data.isPending} error={data.error?.message} empty="no sessions" />
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableBody>
                {sessions.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="max-w-96">
                      <div className="truncate font-medium" title={s.id}>
                        {s.subdir && (
                          <Badge variant="secondary" className="mr-1">
                            {s.subdir}
                          </Badge>
                        )}
                        {s.title}
                      </div>
                      {s.last_prompt && s.last_prompt !== s.title && (
                        <div className="truncate text-xs text-muted-foreground">{s.last_prompt}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-xs whitespace-nowrap text-muted-foreground">{when(s.updated)}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={busy}
                        aria-label={`resume ${s.title}`}
                        onClick={() => resume.mutate([workspace, s.id], { onSuccess: onClose })}
                      >
                        <Play />
                        resume
                      </Button>
                      <ConfirmButton
                        size="xs"
                        variant="ghost"
                        className="text-destructive"
                        disabled={busy}
                        aria-label={`delete ${s.title}`}
                        title={`Delete ${s.title}?`}
                        description={`This deletes the transcript ${s.id}.jsonl; the session can't be resumed after.`}
                        confirm="delete"
                        onConfirm={() => remove.mutate([workspace, s.id])}
                      >
                        <Trash2 />
                      </ConfirmButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
