import type { EventDropArg } from '@fullcalendar/core'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'

import { addDays, daysBetween, filterAssignments, toCalendarEvents, weekdayIndex } from '@/lib/roster'
import type { Assignment, RosterDetail, ShiftTemplate } from '@/types/api'

import type { MatrixProps } from './RosterMatrix'

/**
 * Week / month calendar of assignments. Times are the project's wall-clock times: events are
 * passed without an offset and the calendar runs in UTC, so nothing is shifted to the
 * browser's own timezone.
 */
export function RosterCalendar({ roster, view, editable, filters, onMove, onSelect }: {
  roster: RosterDetail
  view: 'timeGridWeek' | 'dayGridMonth'
  editable: boolean
  filters: MatrixProps['filters']
  onMove: (a: Assignment, dayDelta: number) => void
  onSelect: (analystId: number, date: string) => void
}) {
  const templates = new Map<number, ShiftTemplate>(roster.shift_templates.map((t) => [t.id, t]))
  const analyst = new Map(roster.rows.map((r) => [r.analyst_id, r.employee_code]))
  const project = new Map(roster.projects.map((p) => [p.id, p.code]))
  const events = toCalendarEvents(
    filterAssignments(roster.assignments, filters, templates),
    templates,
    (id) => analyst.get(id) ?? `#${id}`,
    (id) => project.get(id) ?? `#${id}`,
    roster.projects.length > 1,
  ).map((e) => ({ ...e, editable: editable && e.editable }))

  // Weeks start on Monday. Open on the first week that is mostly inside the month and allow
  // the partial weeks at both ends (they show the neighbouring months' days greyed out).
  const firstWeekday = weekdayIndex(roster.start_date)
  const initialDate = view === 'timeGridWeek' && firstWeekday >= 4 ? addDays(roster.start_date, 7 - firstWeekday) : roster.start_date
  const rangeStart = addDays(roster.start_date, -firstWeekday)
  const rangeEnd = addDays(roster.end_date, 7 - weekdayIndex(roster.end_date))

  const handleDrop = (info: EventDropArg) => {
    const a = info.event.extendedProps.assignment as Assignment
    const oldStart = info.oldEvent.startStr.slice(0, 10)
    const newStart = info.event.startStr.slice(0, 10)
    const delta = daysBetween(oldStart, newStart)
    const timeChanged = info.oldEvent.startStr.slice(11, 16) !== info.event.startStr.slice(11, 16)
    info.revert() // the roster reloads from the server after the validated change
    if (timeChanged) return // shift timings come from templates; only the date can be dragged
    if (delta !== 0) onMove(a, delta)
  }

  return (
    <div className="rounded-lg border bg-card p-2" data-testid={`calendar-${view}`}>
      <FullCalendar
        key={view}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={view}
        initialDate={initialDate}
        validRange={{ start: rangeStart, end: rangeEnd }}
        timeZone="UTC"
        firstDay={1}
        height="auto"
        expandRows
        nowIndicator={false}
        allDaySlot={false}
        slotEventOverlap={false}
        eventDisplay="block"
        dayMaxEvents={view === 'dayGridMonth' ? 6 : false}
        headerToolbar={{ left: 'prev,next', center: 'title', right: '' }}
        events={events}
        editable={editable}
        eventDurationEditable={false}
        eventDrop={handleDrop}
        eventClick={(info) => {
          const a = info.event.extendedProps.assignment as Assignment
          onSelect(a.analyst_id, a.date)
        }}
        eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
        slotLabelFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
      />
    </div>
  )
}
