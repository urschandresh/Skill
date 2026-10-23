// Shapes returned by the ShiftOrbit backend (see backend/app/schemas and services).

export interface Skill {
  id: number
  name: string
  description: string
}

export interface ShiftTemplate {
  id: number
  project_id: number
  code: string
  name: string
  start_time: string
  end_time: string
  is_night: boolean
  color: string
  active: boolean
  duration_minutes?: number
  overnight?: boolean
  required_skill_ids?: number[]
}

export interface Staffing {
  id: number
  project_id: number
  shift_template_id: number
  weekday: number | null
  specific_date: string | null
  min_staff: number
  max_staff: number | null
}

export interface Project {
  id: number
  code: string
  name: string
  description: string
  timezone: string
  active: boolean
  required_skill_ids: number[]
  shift_templates: ShiftTemplate[]
  staffing: Staffing[]
}

export interface Eligibility {
  project_id: number
  allowed_shift_codes: string[]
  is_primary: boolean
}

export interface Preferences {
  preferred_shifts: string[]
  avoid_shifts: string[]
  preferred_off_days: number[]
}

export interface Analyst {
  id: number
  employee_code: string
  full_name: string
  email: string | null
  active: boolean
  max_hours_per_week: number | null
  preferences: Partial<Preferences>
  notes: string
  skill_ids: number[]
  eligibility: Eligibility[]
}

export interface Weights {
  fair_nights: number
  fair_weekends: number
  balanced_hours: number
  preferences: number
  shift_changes: number
  disruption: number
}

export interface Policy {
  id: number
  name: string
  is_default: boolean
  working_days_per_week: number
  week_start_day: number
  weekly_mode: 'exact' | 'max'
  max_hours_per_week: number
  max_consecutive_work_days: number
  max_consecutive_nights: number
  min_rest_hours: number
  one_shift_per_day: boolean
  leave_counts_as_working_day: boolean
  solver_time_limit_seconds: number
  weights: Weights
}

export type LeaveStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'

export interface Leave {
  id: number
  analyst_id: number
  start_date: string
  end_date: string
  leave_type: string
  partial_day: boolean
  start_time: string | null
  end_time: string | null
  status: LeaveStatus
  reason: string
  decision_note: string
  source: string
  created_at: string
  decided_at: string | null
}

export interface Holiday {
  id: number
  date: string
  name: string
  project_id: number | null
  blocks_work: boolean
}

export interface Availability {
  id: number
  analyst_id: number
  date: string
  kind: 'unavailable' | 'block_shifts'
  shift_codes: string[]
  note: string
}

export interface CodeMapping {
  id: number
  source_code: string
  target_kind: 'shift' | 'WO' | 'LEAVE' | 'H'
  target_shift_code: string | null
  description: string
}

export interface Assignment {
  id: number
  analyst_id: number
  project_id: number
  shift_template_id: number
  date: string
  locked: boolean
  source: string
  override_reason: string | null
}

export interface RosterCell {
  assignments: Assignment[]
  marker: 'WO' | 'LEAVE' | 'H' | string | null
  leave: { leave_id: number; status: LeaveStatus; partial: boolean; type: string } | null
  holiday: string | null
}

export interface RosterRow {
  analyst_id: number
  employee_code: string
  full_name: string
  cells: Record<string, RosterCell>
}

export type RosterStatus = 'draft' | 'published' | 'archived' | 'historical'

export interface RosterSummary {
  id: number
  year: number
  month: number
  name: string
  status: RosterStatus
  version: number
  parent_roster_id: number | null
  project_ids: number[]
  analyst_ids: number[]
  solver_status: string | null
  solver_summary: Record<string, unknown>
  notes: string
  created_at: string
  updated_at: string
  published_at: string | null
  assignment_count: number
  locked_count: number
}

export interface RosterDetail extends RosterSummary {
  start_date: string
  end_date: string
  assignments: Assignment[]
  rows: RosterRow[]
  projects: { id: number; code: string; name: string }[]
  shift_templates: ShiftTemplate[]
  holidays: { date: string; name: string; blocks_work: boolean }[]
}

export interface Violation {
  rule: string
  severity: 'error' | 'warning'
  message: string
  analyst_id: number | null
  project_id: number | null
  shift_id: number | null
  date: string | null
}

export interface AnalystMetrics {
  shifts: number
  worked_days: number
  nights: number
  weekend_shifts: number
  hours: number
  leave_days: number
  by_code: Record<string, number>
}

export interface ValidationReport {
  is_valid: boolean
  error_count: number
  warning_count: number
  by_rule: Record<string, number>
  violations: Violation[]
  metrics: Record<string, AnalystMetrics>
  coverage_percent: number
  coverage?: { project_id: number; shift_id: number; date: string; required: number; max: number | null; assigned: number }[]
}

export interface FeasibilityIssue {
  type: string
  message: string
  [key: string]: unknown
}

export interface Feasibility {
  ok: boolean
  issues: FeasibilityIssue[]
  warnings: FeasibilityIssue[]
  summary: Record<string, number>
  disclaimer: string
}

export type JobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Job {
  id: string
  kind: 'generate' | 'regenerate' | 'simulate'
  state: JobState
  solver_status: string | null
  roster_id: number | null
  base_roster_id: number | null
  year: number
  month: number
  message: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  time_limit_seconds: number | null
  progress: {
    phase?: string
    elapsed_seconds?: number
    time_limit_seconds?: number
    solutions_found?: number
    objective?: number
    best_bound?: number
    decision_variables?: number
  }
  result: {
    status?: string
    message?: string
    objective?: number | null
    best_bound?: number | null
    wall_time_seconds?: number
    solutions_found?: number
    stopped_by_user?: boolean
    diagnostics?: Record<string, unknown>[]
    objective_breakdown?: Record<string, number>
    validation?: ValidationReport
    preliminary?: Feasibility
    notes?: string[]
    changes?: { removed: number; added: number }
    proven_by?: string
  }
}

export interface Dashboard {
  year: number
  month: number
  totals: { projects: number; active_analysts: number; pending_leaves: number; approved_leaves_this_month: number }
  coverage_percent: number | null
  rosters: (RosterSummary & { is_valid: boolean; error_count: number; coverage_percent: number })[]
  alerts: (Violation & { roster_id: number })[]
  alert_count: number
  shift_distribution: { project: string; shift: string; count: number }[]
  workload: { analyst_id: number; employee_code: string; full_name: string; shifts: number; hours: number; nights: number; weekend_shifts: number; leave_days: number }[]
  pending_leaves: { id: number; analyst_id: number; start_date: string; end_date: string; leave_type: string }[]
  recent_runs: Job[]
}

export interface SlotRef {
  analyst_id: number
  project_id: number
  shift_template_id: number
  date: string
}

export type RosterOp =
  | ({ op: 'add'; locked?: boolean } & SlotRef)
  | ({ op: 'remove' } & SlotRef)
  | ({ op: 'lock' } & SlotRef)
  | ({ op: 'unlock' } & SlotRef)
  | {
      op: 'move'
      from_analyst_id: number
      from_project_id: number
      from_shift_template_id: number
      from_date: string
      to_analyst_id: number
      to_project_id: number
      to_shift_template_id: number
      to_date: string
    }

export interface ChangeResult {
  dry_run: boolean
  committed: boolean
  introduced: Violation[]
  resolved: Violation[]
  validation: ValidationReport
  roster?: RosterDetail
}
