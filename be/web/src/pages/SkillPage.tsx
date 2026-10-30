import { ExternalLink, RefreshCw } from 'lucide-react'
import { useParams } from 'react-router'

import { SectionState } from '@/components/TableSection'
import { Button } from '@/components/ui/button'
import { skillPageKey, useAction, useSkillPage } from '@/hooks/queries'
import { api, skillPageContent } from '@/lib/api'
import { cn } from '@/lib/utils'

const when = (seconds: number) => new Date(seconds * 1000).toLocaleString()

// A page from the pages setting: the newest file its skill wrote, links to the claude.ai artifacts
// its last run published, and a refresh that reruns the skill in the background, polling until
// it's done and then reloading the file
export function SkillPage() {
  const { name = '' } = useParams()
  const page = useSkillPage(name)
  const refresh = useAction(api.refreshSkillPage, [skillPageKey(name)])
  const data = page.data
  if (!data) return <SectionState loading={page.isPending} error={page.error?.message} />
  const running = data.running || refresh.isPending
  return (
    <div className="flex h-[calc(100svh-5rem)] flex-col gap-3">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="font-mono">/{data.skill}</span>
        <span>
          {data.running && data.started_at
            ? `refreshing since ${when(data.started_at)}`
            : data.updated_at
              ? `updated ${when(data.updated_at)}`
              : null}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {data.links.map((url, i) => (
            <Button key={url} variant="outline" size="sm" asChild>
              <a href={url} target="_blank" rel="noreferrer">
                <ExternalLink />
                {data.links.length === 1 ? 'artifact' : `artifact ${i + 1}`}
              </a>
            </Button>
          ))}
          <Button variant="outline" size="sm" disabled={running} onClick={() => refresh.mutate([name])}>
            <RefreshCw className={cn(running && 'animate-spin')} />
            {running ? 'refreshing' : 'refresh'}
          </Button>
        </div>
      </div>
      {data.error && !data.running && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl border border-destructive/50 bg-card p-3 text-xs text-destructive">
          {data.error}
        </pre>
      )}
      {data.file ? (
        // no allow-same-origin: the report's scripts can't reach the API
        <iframe
          title={name}
          src={skillPageContent(name, data.updated_at)}
          sandbox="allow-scripts allow-popups"
          className="min-h-0 w-full flex-1 rounded-xl border bg-white"
        />
      ) : (
        <p className="rounded-xl border bg-card p-6 text-sm text-muted-foreground">
          no output matches <code className="font-mono">{data.output}</code> yet; refresh to run /{data.skill}
        </p>
      )}
    </div>
  )
}
