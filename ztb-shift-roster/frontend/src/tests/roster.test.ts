import { describe, expect, it } from 'vitest'

import {
  addDays, coverageIssuesByDate, daysBetween, emptyHistory, inverseBatch, inverseOp, isWeekend, monthDates,
  moveOp, readableText, recordBatch, redoStep, toCalendarEvents, undoStep, violationIndex, weekdayIndex,
} from '@/lib/roster'
import type { Assignment, RosterOp, ShiftTemplate, Violation } from '@/types/api'

const slot = { analyst_id: 1, project_id: 2, shift_template_id: 3, date: '2026-11-05' }

describe('date helpers', () => {
  it('builds month dates including leap years', () => {
    expect(monthDates(2026, 11)).toHaveLength(30)
    expect(monthDates(2028, 2)).toHaveLength(29)
    expect(monthDates(2026, 12).at(-1)).toBe('2026-12-31')
  })
  it('adds days across month and year boundaries', () => {
    expect(addDays('2026-11-30', 1)).toBe('2026-12-01')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(daysBetween('2026-10-30', '2026-11-02')).toBe(3)
  })
  it('uses Monday = 0 like the backend', () => {
    expect(weekdayIndex('2026-11-02')).toBe(0) // Monday
    expect(weekdayIndex('2026-11-01')).toBe(6) // Sunday
    expect(isWeekend('2026-11-07')).toBe(true)
    expect(isWeekend('2026-11-06')).toBe(false)
  })
})

describe('edit operations and undo/redo', () => {
  it('inverts every op kind', () => {
    expect(inverseOp({ op: 'add', ...slot })).toEqual({ op: 'remove', ...slot })
    expect(inverseOp({ op: 'remove', ...slot })).toEqual({ op: 'add', ...slot })
    expect(inverseOp({ op: 'lock', ...slot })).toEqual({ op: 'unlock', ...slot })
    const mv = moveOp(slot, { ...slot, analyst_id: 9, date: '2026-11-06' })
    expect(inverseOp(inverseOp(mv))).toEqual(mv)
    expect(inverseOp(mv)).toMatchObject({ from_analyst_id: 9, to_analyst_id: 1, to_date: '2026-11-05' })
  })
  it('reverses batches in reverse order', () => {
    const batch: RosterOp[] = [{ op: 'add', ...slot }, { op: 'lock', ...slot }]
    expect(inverseBatch(batch)).toEqual([{ op: 'unlock', ...slot }, { op: 'remove', ...slot }])
  })
  it('walks history back and forward', () => {
    const a: RosterOp[] = [{ op: 'add', ...slot }]
    const b: RosterOp[] = [{ op: 'lock', ...slot }]
    let h = recordBatch(recordBatch(emptyHistory, a), b)
    const u1 = undoStep(h)!
    expect(u1.ops).toEqual([{ op: 'unlock', ...slot }])
    h = u1.next
    expect(h.future).toEqual([b])
    const r1 = redoStep(h)!
    expect(r1.ops).toEqual(b)
    expect(r1.next.past).toEqual([a, b])
    expect(undoStep(emptyHistory)).toBeNull()
    expect(redoStep(r1.next)).toBeNull()
    // A new edit clears the redo stack.
    expect(recordBatch(h, a).future).toEqual([])
  })
})

describe('view helpers', () => {
  const v = (over: Partial<Violation>): Violation => ({ rule: 'min_rest', severity: 'error', message: 'x',
    analyst_id: 1, project_id: null, shift_id: null, date: '2026-11-05', ...over })
  it('indexes errors by analyst and day, ignoring warnings', () => {
    const idx = violationIndex([v({}), v({ severity: 'warning' }), v({ analyst_id: null })])
    expect(idx.get('1|2026-11-05')).toHaveLength(1)
    expect(idx.size).toBe(1)
  })
  it('groups coverage issues by date', () => {
    const idx = coverageIssuesByDate([v({ rule: 'coverage' }), v({ rule: 'coverage_max', date: '2026-11-06' }), v({})])
    expect([...idx.keys()]).toEqual(['2026-11-05', '2026-11-06'])
  })
  it('creates overnight calendar events ending the next day', () => {
    const t: ShiftTemplate = { id: 3, project_id: 2, code: 'N', name: 'Night', start_time: '22:00', end_time: '07:00',
      is_night: true, color: '#6366f1', active: true }
    const a: Assignment = { id: 7, ...slot, locked: true, source: 'solver', override_reason: null }
    const [e] = toCalendarEvents([a], new Map([[3, t]]), () => 'SYN-1', () => 'P', false)
    expect(e.start).toBe('2026-11-05T22:00:00')
    expect(e.end).toBe('2026-11-06T07:00:00')
    expect(e.editable).toBe(false)
    expect(e.title).toContain('🔒')
  })
  it('picks readable text colours', () => {
    expect(readableText('#ffffff')).toBe('#0a1628')
    expect(readableText('#0a1628')).toBe('#ffffff')
  })
})
