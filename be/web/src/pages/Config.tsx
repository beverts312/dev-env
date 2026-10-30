import { useState, type FormEvent, type ReactNode } from 'react'
import { Eye, EyeOff, Plus } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { SectionState } from '@/components/TableSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAction } from '@/hooks/queries'
import { api, type Setting } from '@/lib/api'
import { cn } from '@/lib/utils'

// the select's stand-in for no value, which Radix can't hold
const UNSET = '__unset__'

// Every setting with its file value to edit, its source and help; each saves on its own
export function Config() {
  const config = useQuery({ queryKey: ['config'], queryFn: api.config })
  const data = config.data
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Saved to <code className="rounded bg-muted px-1 py-0.5 text-xs">{data?.path ?? '…'}</code>. An env var wins
        over the file; saving an empty value removes it.
      </p>
      {!data?.settings.length ? (
        <SectionState loading={config.isPending} error={config.error?.message ?? data?.error} empty="no settings" />
      ) : (
        <div className="divide-y rounded-xl border bg-card">
          {data.settings.map((s) =>
            s.kind === 'map' ? (
              <MapSetting key={s.key} setting={s} />
            ) : s.kind === 'tables' ? (
              <TablesSetting key={s.key} setting={s} />
            ) : (
              <SettingRow key={`${s.key}=${s.value}`} setting={s} />
            ),
          )}
        </div>
      )}
    </div>
  )
}

// the agent the reviews page starts on is pr.agent, so meta changes with the config
const CHANGES = [['config'], ['meta']]

function Row({ setting, children }: { setting: Setting; children: ReactNode }) {
  return (
    <div className="grid gap-3 p-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm">{setting.key}</span>
          <Badge variant={setting.source === 'file' ? 'secondary' : 'outline'} className="font-normal">
            {setting.source}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{setting.help}</p>
        {setting.notes.map((n) => (
          <p key={n} className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            {n}
          </p>
        ))}
      </div>
      <div className="min-w-0 space-y-2">{children}</div>
    </div>
  )
}

function SettingRow({ setting }: { setting: Setting }) {
  const [value, setValue] = useState(setting.value ?? '')
  const save = useAction(api.setConfig, CHANGES)
  const unset = useAction(api.unsetConfig, CHANGES)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate([setting.key, value])
  }
  return (
    <Row setting={setting}>
      <form onSubmit={submit} className="flex gap-2">
        <ValueInput setting={setting} value={value} onChange={setValue} />
        <Button type="submit" size="sm" disabled={save.isPending}>
          save
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={unset.isPending || !setting.value}
          onClick={() => unset.mutate([setting.key])}
        >
          unset
        </Button>
      </form>
    </Row>
  )
}

// a table of tables, shown but not edited here: set its fields with `be config set`
function TablesSetting({ setting }: { setting: Setting }) {
  const tables = Object.entries((setting.entries ?? {}) as Record<string, Record<string, string>>)
  return (
    <Row setting={setting}>
      {tables.map(([name, fields]) => (
        <div key={name} className="rounded-md border p-2 text-xs">
          <div className="font-mono font-medium">{name}</div>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            {Object.entries(fields).map(([field, v]) => (
              <div key={field} className="contents">
                <dt className="text-muted-foreground">{field}</dt>
                <dd className="truncate font-mono">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      <p className="text-xs text-muted-foreground">
        {tables.length ? '' : 'none in the file. '}Set with{' '}
        <code className="rounded bg-muted px-1 py-0.5">
          be config set {setting.key}.&lt;name&gt;.&lt;{(setting.fields ?? []).join('|')}&gt; …
        </code>
      </p>
    </Row>
  )
}

function MapSetting({ setting }: { setting: Setting }) {
  const entries = Object.entries((setting.entries ?? {}) as Record<string, string>)
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const add = useAction(api.setConfig, CHANGES)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate([setting.key, value, name], {
      onSuccess: () => {
        setName('')
        setValue('')
      },
    })
  }
  return (
    <Row setting={setting}>
      <p className="text-xs text-muted-foreground">
        {entries.length} entr{entries.length === 1 ? 'y' : 'ies'} in the file
      </p>
      {entries.map(([entry, v]) => (
        <MapEntry key={`${entry}=${v}`} setting={setting} entry={entry} value={v} />
      ))}
      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="NAME"
          aria-label={`new ${setting.key} name`}
          className="w-32 font-mono"
        />
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="description"
          aria-label={`new ${setting.key} description`}
        />
        <Button type="submit" size="sm" variant="outline" disabled={add.isPending}>
          <Plus />
          add
        </Button>
      </form>
    </Row>
  )
}

function MapEntry({ setting, entry, value: initial }: { setting: Setting; entry: string; value: string }) {
  const key = `${setting.key}.${entry}`
  const [value, setValue] = useState(initial)
  const save = useAction(api.setConfig, CHANGES)
  const remove = useAction(api.unsetConfig, CHANGES)
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate([key, value])
      }}
      className="flex items-center gap-2"
    >
      <span className="w-32 shrink-0 truncate font-mono text-xs" title={key}>
        {entry}
      </span>
      <Input value={value} onChange={(e) => setValue(e.target.value)} aria-label={key} />
      <Button type="submit" size="sm" disabled={save.isPending}>
        save
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={remove.isPending}
        onClick={() => remove.mutate([key])}
      >
        remove
      </Button>
    </form>
  )
}

// a dropdown of the setting's choices (with a blank naming its default, and any other value the file
// has), a password box with a show button if it's secret, else a text box showing its default
function ValueInput({ setting, value, onChange }: { setting: Setting; value: string; onChange: (v: string) => void }) {
  const [reveal, setReveal] = useState(false)
  if (setting.choices.length) {
    const options = value && !setting.choices.includes(value) ? [...setting.choices, value] : setting.choices
    return (
      <Select value={value || UNSET} onValueChange={(v) => onChange(v === UNSET ? '' : v)}>
        <SelectTrigger className="w-full" aria-label={setting.key}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={UNSET}>{setting.default ? `(default: ${setting.default})` : '(unset)'}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }
  return (
    <div className="relative w-full">
      <Input
        type={setting.secret && !reveal ? 'password' : 'text'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={setting.default ?? ''}
        aria-label={setting.key}
        autoComplete="off"
        className={cn(setting.secret && 'pr-9')}
      />
      {setting.secret && (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="absolute top-1/2 right-1.5 -translate-y-1/2"
          aria-label={reveal ? 'hide' : 'show'}
          aria-pressed={reveal}
          onClick={() => setReveal(!reveal)}
        >
          {reveal ? <EyeOff /> : <Eye />}
        </Button>
      )}
    </div>
  )
}

