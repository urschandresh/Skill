import { describe, expect, it } from 'vitest'

import { leaveSchema, projectSchema, shiftMinutes, splitCodes, templateSchema } from '@/lib/forms'

describe('form validation', () => {
  it('computes overnight durations', () => {
    expect(shiftMinutes('22:00', '07:00')).toBe(540)
    expect(shiftMinutes('06:00', '15:00')).toBe(540)
  })
  it('rejects reserved or invalid shift templates', () => {
    const ok = { code: 'D', name: 'Day', start_time: '09:00', end_time: '18:00', is_night: false, color: '#22c55e', active: true }
    expect(templateSchema.safeParse(ok).success).toBe(true)
    expect(templateSchema.safeParse({ ...ok, code: 'WO' }).success).toBe(false)
    expect(templateSchema.safeParse({ ...ok, end_time: '09:30' }).success).toBe(false)
    expect(templateSchema.safeParse({ ...ok, start_time: '25:00' }).success).toBe(false)
  })
  it('rejects control characters and bad codes in projects', () => {
    const ok = { code: 'SOC1', name: 'SOC', description: '', timezone: 'Asia/Kolkata', active: true }
    expect(projectSchema.safeParse(ok).success).toBe(true)
    expect(projectSchema.safeParse({ ...ok, name: 'bad\u0000' }).success).toBe(false)
    expect(projectSchema.safeParse({ ...ok, code: '=cmd' }).success).toBe(false)
  })
  it('validates leave dates and partial days', () => {
    const base = { analyst_id: '1', start_date: '2026-11-03', end_date: '2026-11-03', leave_type: 'annual' as const,
      partial_day: false, start_time: '', end_time: '', reason: '' }
    expect(leaveSchema.safeParse(base).success).toBe(true)
    expect(leaveSchema.safeParse({ ...base, end_date: '2026-11-01' }).success).toBe(false)
    expect(leaveSchema.safeParse({ ...base, partial_day: true }).success).toBe(false)
    expect(leaveSchema.safeParse({ ...base, partial_day: true, start_time: '09:00', end_time: '13:00' }).success).toBe(true)
    expect(leaveSchema.safeParse({ ...base, partial_day: true, end_date: '2026-11-04', start_time: '09:00', end_time: '13:00' }).success).toBe(false)
  })
  it('splits code lists', () => {
    expect(splitCodes(' m, a ;n ')).toEqual(['M', 'A', 'N'])
  })
})
