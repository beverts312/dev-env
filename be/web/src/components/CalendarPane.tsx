import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, FileText, RefreshCw, Video } from 'lucide-react'

import { SectionState } from '@/components/TableSection'
import { Button } from '@/components/ui/button'
import { useCalendar } from '@/hooks/queries'
import type { CalEvent } from '@/lib/api'
import { addDays, localDay, parseDay } from '@/lib/days'
import { cn } from '@/lib/utils'

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

// The right edge of the home page: one day of your Google Calendar, today unless you step to another
export function CalendarPane() {
  const now = useNow()
  const today = localDay(now)
  const [day, setDay] = useState(today)
  const query = useCalendar(day, day === today)
  // the last day's answer stays, faded, while this one loads
  const data = query.data
  const stale = data !== undefined && data.day !== day
  const events = data?.events ?? []
  const allDay = events.filter((e) => e.all_day)
  const timed = events.filter((e) => !e.all_day)
  const label = parseDay(day).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })

  return (
    <section aria-label="calendar" className="rounded-xl border bg-card text-card-foreground shadow-xs">
      <header className="flex items-center gap-1 px-2 py-2.5">
        <Button variant="ghost" size="icon-sm" aria-label="previous day" onClick={() => setDay(addDays(day, -1))}>
          <ChevronLeft />
        </Button>
        <label className="relative cursor-pointer text-sm font-semibold">
          {label}
          <input
            type="date"
            aria-label="pick a day"
            value={day}
            onChange={(e) => e.target.value && setDay(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
        <Button variant="ghost" size="icon-sm" aria-label="next day" onClick={() => setDay(addDays(day, 1))}>
          <ChevronRight />
        </Button>
        {day !== today && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setDay(today)}>
            today
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="refresh calendar"
          className="ml-auto text-muted-foreground"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <RefreshCw className={cn(query.isFetching && 'animate-spin')} />
        </Button>
      </header>
      <div className={cn('border-t transition-opacity', stale && 'opacity-50')}>
        {!data || data.error || !events.length ? (
          <SectionState
            loading={!data && !query.error}
            error={query.error?.message ?? data?.error}
            empty={`nothing on ${label}`}
          />
        ) : (
          <>
            {allDay.length > 0 && (
              <ul className="flex flex-wrap gap-1 border-b p-2">
                {allDay.map((e) => (
                  <li key={e.id} className="rounded-md bg-muted px-2 py-0.5 text-xs">
                    <EventTitle event={e} />
                  </li>
                ))}
              </ul>
            )}
            <ul className="divide-y">
              {timed.map((e) => {
                const past = new Date(e.end) <= now
                const current = !past && new Date(e.start) <= now
                return (
                  <li
                    key={e.id}
                    data-current={current || undefined}
                    className={cn(
                      'flex gap-3 px-3 py-2 text-sm',
                      past && 'opacity-50',
                      current && 'bg-primary/10',
                      e.response !== 'accepted' && 'text-muted-foreground',
                    )}
                  >
                    <span className="w-28 shrink-0 text-xs text-muted-foreground tabular-nums">
                      {time(e.start)} – {time(e.end)}
                    </span>
                    <div className="flex min-w-0 flex-1 items-start gap-1">
                      <span className="min-w-0 flex-1 break-words">
                        <EventTitle event={e} />
                      </span>
                      {e.doc_url && (
                        <a
                          href={e.doc_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`meeting doc for ${e.title}`}
                          className="text-muted-foreground hover:text-primary"
                        >
                          <FileText className="size-4" />
                        </a>
                      )}
                      {e.meet_url && (
                        <a
                          href={e.meet_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`join ${e.title}`}
                          className="text-muted-foreground hover:text-primary"
                        >
                          <Video className="size-4" />
                        </a>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}

function EventTitle({ event }: { event: CalEvent }) {
  if (!event.html_link) return <>{event.title}</>
  return (
    <a href={event.html_link} target="_blank" rel="noreferrer" className="hover:underline">
      {event.title}
    </a>
  )
}

// the time now, updated each minute, for marking what's past and what's on
function useNow() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}
