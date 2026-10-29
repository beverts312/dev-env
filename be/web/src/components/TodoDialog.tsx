import { useState, type FormEvent } from 'react'
import { Trash2 } from 'lucide-react'

import { ConfirmButton } from '@/components/ConfirmButton'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { todosKey, useAction } from '@/hooks/queries'
import { api, type Todo } from '@/lib/api'

const NONE = 'none'

// Edits a todo's fields and notes, which are its file's frontmatter and body, or deletes the file.
// Mount it with a key per todo, so each opens fresh.
export function TodoDialog({ todo, onClose }: { todo: Todo; onClose: () => void }) {
  const [title, setTitle] = useState(todo.title)
  const [due, setDue] = useState(todo.due ?? '')
  const [priority, setPriority] = useState<string>(todo.priority ?? NONE)
  const [jira, setJira] = useState(todo.jira ?? '')
  const [tags, setTags] = useState(todo.tags.join(', '))
  const [notes, setNotes] = useState(todo.notes)
  const save = useAction(api.updateTodo, [todosKey])
  const remove = useAction(api.deleteTodo, [todosKey])
  const busy = save.isPending || remove.isPending

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate(
      [
        todo.id,
        {
          title: title.trim(),
          due: due.trim(),
          priority: priority === NONE ? '' : priority,
          jira: jira.trim(),
          tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
          notes,
        },
      ],
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Edit todo</DialogTitle>
            <DialogDescription className="font-mono text-xs">{todo.id}.md</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="todo-title">title</Label>
            <Input id="todo-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="todo-due">due</Label>
              <Input
                id="todo-due"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                placeholder="YYYY-MM-DD, +3d"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="todo-priority">priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger id="todo-priority" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[NONE, 'high', 'med', 'low'].map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="todo-jira">jira</Label>
              <Input id="todo-jira" value={jira} onChange={(e) => setJira(e.target.value)} placeholder="ADC-123" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="todo-tags">tags</Label>
            <Input id="todo-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="comma separated" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="todo-notes">notes</Label>
            <textarea
              id="todo-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={8}
              placeholder="markdown"
              className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          <DialogFooter className="sm:justify-between">
            <ConfirmButton
              type="button"
              variant="ghost"
              className="text-destructive"
              title={`Delete ${todo.title}?`}
              description={`This deletes ${todo.id}.md.`}
              confirm="delete"
              disabled={busy}
              onConfirm={() => remove.mutate([todo.id], { onSuccess: onClose })}
            >
              <Trash2 />
              delete
            </ConfirmButton>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                cancel
              </Button>
              <Button type="submit" disabled={busy || !title.trim()}>
                save
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
