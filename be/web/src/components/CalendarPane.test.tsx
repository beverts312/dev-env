import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { CalendarPane } from '@/components/CalendarPane'
import type { CalEvent } from '@/lib/api'
import { addDays, localDay } from '@/lib/days'
import { mockApi, renderApp } from '@/test/render'

const tz = encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)
const today = localDay(new Date())

function event(id: string, fields: Partial<CalEvent> = {}): CalEvent {
  return {
    id,
    title: id,
    start: `${today}T09:00:00`,
    end: `${today}T09:30:00`,
    all_day: false,
    html_link: `https://calendar.google.com/event?eid=${id}`,
    meet_url: null,
    doc_url: null,
    location: '',
    response: 'accepted',
    attendees: 2,
    ...fields,
  }
}

const dayOf = (day: string, events: CalEvent[], error: string | null = null) => ({ day, events, error, fetched_at: 0 })

describe('CalendarPane', () => {
  it('shows today’s events with their meeting docs', async () => {
    mockApi({
      [`GET /calendar?day=${today}&tz=${tz}`]: dayOf(today, [
        event('Offsite', { all_day: true, start: today, end: addDays(today, 1) }),
        event('Standup', { doc_url: 'https://docs.google.com/document/d/notes', meet_url: 'https://meet.google.com/x' }),
      ]),
    })
    renderApp(<CalendarPane />)
    expect(await screen.findByRole('link', { name: 'Standup' })).toHaveAttribute('href', 'https://calendar.google.com/event?eid=Standup')
    expect(screen.getByRole('link', { name: 'meeting doc for Standup' })).toHaveAttribute('href', 'https://docs.google.com/document/d/notes')
    expect(screen.getByRole('link', { name: 'join Standup' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Offsite' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'today' })).not.toBeInTheDocument()
  })

  it('steps to another day and back to today', async () => {
    const tomorrow = addDays(today, 1)
    const calls = mockApi({
      [`GET /calendar?day=${today}&tz=${tz}`]: dayOf(today, [event('Standup')]),
      [`GET /calendar?day=${tomorrow}&tz=${tz}`]: dayOf(tomorrow, [event('Retro')]),
    })
    renderApp(<CalendarPane />)
    await screen.findByText('Standup')
    await userEvent.click(screen.getByRole('button', { name: 'next day' }))
    expect(await screen.findByText('Retro')).toBeInTheDocument()
    expect(calls.map((c) => c.path)).toContain(`/calendar?day=${tomorrow}&tz=${tz}`)
    await userEvent.click(screen.getByRole('button', { name: 'today' }))
    expect(await screen.findByText('Standup')).toBeInTheDocument()
  })

  it('shows why the calendar couldn’t be read', async () => {
    mockApi({
      [`GET /calendar?day=${today}&tz=${tz}`]: dayOf(today, [], 'not signed in to Google; run `be calendar login`'),
    })
    renderApp(<CalendarPane />)
    expect(await screen.findByText('not signed in to Google; run `be calendar login`')).toBeInTheDocument()
  })
})

describe('addDays', () => {
  it('crosses months', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })
})
