import { z } from 'zod'

// Client-side mirrors of the backend validation. The backend remains the authority.

export const hhmm = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Use 24-hour HH:MM')
// oxlint-disable-next-line no-control-regex -- rejecting control characters is the point
const noControl = (s: string) => !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(s)

export const projectSchema = z.object({
  code: z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$/, '1–16 letters, digits, _ or -'),
  name: z.string().trim().min(1, 'Required').max(120).refine(noControl, 'Invalid characters'),
  description: z.string().max(4000).refine(noControl, 'Invalid characters'),
  timezone: z.string().min(1).max(64),
  active: z.boolean(),
})
export type ProjectForm = z.infer<typeof projectSchema>

export function shiftMinutes(start: string, end: string): number {
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  let e = eh * 60 + em
  const s = sh * 60 + sm
  if (e <= s) e += 24 * 60
  return e - s
}

export const templateSchema = z
  .object({
    code: z.string().trim().regex(/^[A-Za-z][A-Za-z0-9]{0,7}$/, '1–8 letters/digits starting with a letter')
      .refine((c) => !['WO', 'LEAVE', 'H', 'OFF'].includes(c.toUpperCase()), 'Reserved for non-working days'),
    name: z.string().trim().min(1).max(64),
    start_time: hhmm,
    end_time: hhmm,
    is_night: z.boolean(),
    color: z.string().regex(/^#[0-9a-fA-F]{6}$/, 'Hex colour like #2f80ed'),
    active: z.boolean(),
  })
  .refine((v) => {
    if (!hhmm.safeParse(v.start_time).success || !hhmm.safeParse(v.end_time).success) return true
    const m = shiftMinutes(v.start_time, v.end_time)
    return m >= 60 && m <= 16 * 60
  }, { message: 'Shift must last between 1 and 16 hours', path: ['end_time'] })
export type TemplateForm = z.infer<typeof templateSchema>

export const staffingSchema = z
  .object({
    shift_template_id: z.string().min(1, 'Choose a shift'),
    day: z.string(), // "" = every day, "0".."6" = weekday, "date" = specific date
    specific_date: z.string(),
    min_staff: z.string().regex(/^\d{1,3}$/, 'Whole number'),
    max_staff: z.string(),
  })
  .refine((v) => v.day !== 'date' || /^\d{4}-\d{2}-\d{2}$/.test(v.specific_date), {
    message: 'Pick a date', path: ['specific_date'],
  })
  .refine((v) => v.max_staff === '' || Number(v.max_staff) >= Number(v.min_staff), {
    message: 'Maximum must be at least the minimum', path: ['max_staff'],
  })
export type StaffingForm = z.infer<typeof staffingSchema>

export const analystSchema = z.object({
  employee_code: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/, '1–32 letters, digits, . _ -'),
  full_name: z.string().trim().min(1, 'Required').max(120).refine(noControl, 'Invalid characters'),
  email: z.union([z.literal(''), z.string().regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, 'Invalid email')]),
  active: z.boolean(),
  max_hours_per_week: z.string().regex(/^$|^\d{1,2}$/, 'Whole hours'),
  notes: z.string().max(4000),
  preferred_shifts: z.string(),
  avoid_shifts: z.string(),
  preferred_off_days: z.array(z.number().int().min(0).max(6)),
  skill_ids: z.array(z.number()),
  eligibility: z.array(z.object({
    project_id: z.number(),
    allowed_shift_codes: z.string(),
    is_primary: z.boolean(),
  })),
})
export type AnalystForm = z.infer<typeof analystSchema>

export const leaveSchema = z
  .object({
    analyst_id: z.string().min(1, 'Choose an analyst'),
    start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Required'),
    end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Required'),
    leave_type: z.enum(['annual', 'sick', 'casual', 'comp_off', 'unpaid', 'other']),
    partial_day: z.boolean(),
    start_time: z.string(),
    end_time: z.string(),
    reason: z.string().max(4000),
  })
  .refine((v) => v.end_date >= v.start_date, { message: 'End must be on or after start', path: ['end_date'] })
  .refine((v) => !v.partial_day || v.start_date === v.end_date, {
    message: 'Partial-day leave is for a single date', path: ['end_date'],
  })
  .refine((v) => !v.partial_day || (hhmm.safeParse(v.start_time).success && hhmm.safeParse(v.end_time).success
    && v.end_time > v.start_time), { message: 'Give a start and later end time', path: ['end_time'] })
export type LeaveForm = z.infer<typeof leaveSchema>

export function splitCodes(s: string): string[] {
  return s.split(/[\s,;]+/).map((x) => x.trim().toUpperCase()).filter(Boolean)
}
