// Pure roster helpers: date maths, edit operations, undo/redo history and view filters.

import type { Assignment, RosterOp, ShiftTemplate, SlotRef, Violation } from '@/types/api'

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const

/** Dates are handled as ISO strings (YYYY-MM-DD) and computed in UTC to avoid DST drift. */
export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

export function toISODate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

export function addDays(iso: string, days: number): string {
  const d = parseISODate(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return toISODate(d)
}

export function daysBetween(a: string, b: string): number {
  return Math.round((parseISODate(b).getTime() - parseISODate(a).getTime()) / 86_400_000)
}

export function monthDates(year: number, month: number): string[] {
  const out: string[] = []
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  for (let d = 1; d <= days; d++) out.push(`${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
  return out
}

/** Monday = 0 ... Sunday = 6 (matches the backend). */
export function weekdayIndex(iso: string): number {
  return (parseISODate(iso).getUTCDay() + 6) % 7
}

export function isWeekend(iso: string): boolean {
  return weekdayIndex(iso) >= 5
}

export function slotOf(a: Assignment | SlotRef): SlotRef {
  return { analyst_id: a.analyst_id, project_id: a.project_id, shift_template_id: a.shift_template_id, date: a.date }
}

export function slotKey(s: SlotRef): string {
  return `${s.analyst_id}|${s.project_id}|${s.shift_template_id}|${s.date}`
}

export function moveOp(from: SlotRef, to: SlotRef): RosterOp {
  return {
    op: 'move',
    from_analyst_id: from.analyst_id,
    from_project_id: from.project_id,
    from_shift_template_id: from.shift_template_id,
    from_date: from.date,
    to_analyst_id: to.analyst_id,
    to_project_id: to.project_id,
    to_shift_template_id: to.shift_template_id,
    to_date: to.date,
  }
}

/** The operation that undoes `op`. */
export function inverseOp(op: RosterOp): RosterOp {
  switch (op.op) {
    case 'add':
      return { op: 'remove', ...slotOf(op) }
    case 'remove':
      return { op: 'add', ...slotOf(op) }
    case 'lock':
      return { op: 'unlock', ...slotOf(op) }
    case 'unlock':
      return { op: 'lock', ...slotOf(op) }
    case 'move':
      return {
        op: 'move',
        from_analyst_id: op.to_analyst_id,
        from_project_id: op.to_project_id,
        from_shift_template_id: op.to_shift_template_id,
        from_date: op.to_date,
        to_analyst_id: op.from_analyst_id,
        to_project_id: op.from_project_id,
        to_shift_template_id: op.from_shift_template_id,
        to_date: op.from_date,
      }
  }
}

/** Inverse of a batch: inverse of each op, in reverse order. */
export function inverseBatch(ops: RosterOp[]): RosterOp[] {
  return [...ops].reverse().map(inverseOp)
}

export interface History {
  past: RosterOp[][]
  future: RosterOp[][]
}

export const emptyHistory: History = { past: [], future: [] }

export function recordBatch(h: History, ops: RosterOp[]): History {
  return { past: [...h.past, ops].slice(-100), future: [] }
}

/** Returns the ops to send for an undo and the history after it succeeds. */
export function undoStep(h: History): { ops: RosterOp[]; next: History } | null {
  const last = h.past[h.past.length - 1]
  if (!last) return null
  return { ops: inverseBatch(last), next: { past: h.past.slice(0, -1), future: [last, ...h.future] } }
}

export function redoStep(h: History): { ops: RosterOp[]; next: History } | null {
  const first = h.future[0]
  if (!first) return null
  return { ops: first, next: { past: [...h.past, first], future: h.future.slice(1) } }
}

/** Violations indexed by "analystId|date" for highlighting matrix cells. */
export function violationIndex(violations: Violation[]): Map<string, Violation[]> {
  const map = new Map<string, Violation[]>()
  for (const v of violations) {
    if (v.severity !== 'error' || v.analyst_id == null || !v.date) continue
    const key = `${v.analyst_id}|${v.date}`
    map.set(key, [...(map.get(key) ?? []), v])
  }
  return map
}

/** Coverage problems indexed by date for highlighting matrix columns. */
export function coverageIssuesByDate(violations: Violation[]): Map<string, Violation[]> {
  const map = new Map<string, Violation[]>()
  for (const v of violations) {
    if (!v.date || !(v.rule === 'coverage' || v.rule === 'coverage_max')) continue
    map.set(v.date, [...(map.get(v.date) ?? []), v])
  }
  return map
}

export interface CalendarEventInput {
  id: string
  title: string
  start: string
  end: string
  backgroundColor: string
  borderColor: string
  editable: boolean
  extendedProps: { assignment: Assignment }
}

/** Assignments as FullCalendar events (wall-clock times of the project timezone). */
export function toCalendarEvents(
  assignments: Assignment[],
  templates: Map<number, ShiftTemplate>,
  analystLabel: (id: number) => string,
  projectLabel: (id: number) => string,
  showProject: boolean,
): CalendarEventInput[] {
  return assignments.flatMap((a) => {
    const t = templates.get(a.shift_template_id)
    if (!t) return []
    const endDate = t.end_time <= t.start_time ? addDays(a.date, 1) : a.date
    const prefix = showProject ? `${projectLabel(a.project_id)} ` : ''
    return [{
      id: String(a.id),
      title: `${prefix}${t.code} · ${analystLabel(a.analyst_id)}${a.locked ? ' 🔒' : ''}`,
      start: `${a.date}T${t.start_time}:00`,
      end: `${endDate}T${t.end_time}:00`,
      backgroundColor: t.color,
      borderColor: a.locked ? '#ffffff' : t.color,
      editable: !a.locked,
      extendedProps: { assignment: a },
    }]
  })
}

export function filterAssignments(
  assignments: Assignment[],
  f: { projectId?: number | null; analystId?: number | null; shiftCode?: string | null },
  templates: Map<number, ShiftTemplate>,
): Assignment[] {
  return assignments.filter(
    (a) =>
      (f.projectId == null || a.project_id === f.projectId) &&
      (f.analystId == null || a.analyst_id === f.analystId) &&
      (f.shiftCode == null || templates.get(a.shift_template_id)?.code === f.shiftCode),
  )
}

/** Text colour that stays readable on a shift colour. */
export function readableText(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!m) return '#0a1628'
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? '#0a1628' : '#ffffff'
}
