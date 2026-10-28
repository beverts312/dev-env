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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useAction } from '@/hooks/queries'
import { api, type Issue } from '@/lib/api'

const ON = 'data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

// Asks before creating a workspace for an issue that has none, as `jira ls -i` does, or linking it to
// one that exists. The new one is named after the issue, or its Feature or Epic parent, and takes that
// one's summary. Mount it with a key per issue, so each opens fresh.
export function WorkspaceDialog({
  issue,
  workspaces,
  onClose,
}: {
  issue: Issue
  workspaces: string[]
  onClose: () => void
}) {
  const [forParent, setForParent] = useState(false)
  const [mode, setMode] = useState<'create' | 'link'>('create')
  const [name, setName] = useState(issue.key)
  const [repos, setRepos] = useState('')
  const [extraDirs, setExtraDirs] = useState('')
  const [description, setDescription] = useState('')
  const [linkTo, setLinkTo] = useState(workspaces[0] ?? '')
  const create = useAction(api.createWorkspace, ['workspaces', 'jira'])
  const link = useAction(api.linkWorkspace, ['workspaces', 'jira'])
  const busy = create.isPending || link.isPending

  const key = forParent ? issue.parent : issue.key
  const pickFor = (parent: boolean) => {
    setForParent(parent)
    setName(parent ? issue.parent : issue.key)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const done = { onSuccess: onClose }
    if (mode === 'link') {
      link.mutate([linkTo, key], done)
      return
    }
    create.mutate(
      [
        {
          name: name.trim(),
          repos,
          extra_dirs: extraDirs,
          description,
          issue_name: forParent ? issue.parent_summary : issue.summary,
        },
      ],
      done,
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>
              No workspace for <span className="font-mono">{issue.key}</span>
            </DialogTitle>
            <DialogDescription className="line-clamp-2">{issue.summary}</DialogDescription>
          </DialogHeader>

          {issue.parent_offer && (
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-xs text-muted-foreground">workspace for</legend>
              <RadioGroup value={forParent ? 'parent' : 'issue'} onValueChange={(v) => pickFor(v === 'parent')}>
                <Label className="font-normal">
                  <RadioGroupItem value="issue" /> {issue.key} only
                </Label>
                <Label className="font-normal">
                  <RadioGroupItem value="parent" /> its {issue.parent_type} {issue.parent}
                  {issue.parent_summary && <span className="text-muted-foreground">({issue.parent_summary})</span>}
                </Label>
              </RadioGroup>
            </fieldset>
          )}

          {workspaces.length > 0 && (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={mode}
              onValueChange={(v) => v && setMode(v as 'create' | 'link')}
              aria-label="new or existing workspace"
            >
              <ToggleGroupItem value="create" className={ON}>create a new one</ToggleGroupItem>
              <ToggleGroupItem value="link" className={ON}>link an existing one</ToggleGroupItem>
            </ToggleGroup>
          )}

          {mode === 'create' ? (
            <div className="grid gap-3">
              <Field label="name">
                <Input value={name} onChange={(e) => setName(e.target.value)} required />
              </Field>
              <Field label="repos">
                <Input value={repos} onChange={(e) => setRepos(e.target.value)} placeholder="comma separated" autoFocus />
              </Field>
              <Field label="extra dirs">
                <Input value={extraDirs} onChange={(e) => setExtraDirs(e.target.value)} placeholder="comma separated" />
              </Field>
              <Field label="description">
                <Input value={description} onChange={(e) => setDescription(e.target.value)} />
              </Field>
            </div>
          ) : (
            <Field label="workspace">
              <Select value={linkTo} onValueChange={setLinkTo}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {workspaces.map((w) => (
                    <SelectItem key={w} value={w}>
                      {w}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {mode === 'link' ? `link ${key} and open` : 'create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}
