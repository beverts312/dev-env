import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useAction } from '@/hooks/queries'
import { api } from '@/lib/api'

// Asks what the cloud issue is about, then opens a cmux workspace running claude's /cloud-issue on it
export function CloudIssueDialog({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState('')
  const file = useAction(api.cloudIssue)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    file.mutate([text.trim()], { onSuccess: onClose })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New Cloud issue</DialogTitle>
            <DialogDescription>runs /cloud-issue in claude</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="cloud-issue-text">what needs doing</Label>
            <textarea
              id="cloud-issue-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              autoFocus
              required
              className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              cancel
            </Button>
            <Button type="submit" disabled={file.isPending || !text.trim()}>
              create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
