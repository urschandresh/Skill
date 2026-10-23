import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ShiftChip, ViolationList } from '@/components/common'
import { MonthPicker } from '@/components/MonthPicker'
import { RosterMatrix } from '@/components/roster/RosterMatrix'
import type { RosterDetail, ValidationReport } from '@/types/api'

const roster: RosterDetail = {
  id: 1, year: 2026, month: 11, name: '2026-11 v1', status: 'draft', version: 1, parent_roster_id: null,
  project_ids: [1], analyst_ids: [10, 11], solver_status: 'OPTIMAL', solver_summary: {}, notes: '',
  created_at: '', updated_at: '', published_at: null, assignment_count: 1, locked_count: 0,
  start_date: '2026-11-01', end_date: '2026-11-03',
  assignments: [{ id: 5, analyst_id: 10, project_id: 1, shift_template_id: 100, date: '2026-11-02', locked: false, source: 'solver', override_reason: null }],
  rows: [
    { analyst_id: 10, employee_code: 'SYN-001', full_name: 'Synthetic One', cells: {
      '2026-11-01': { assignments: [], marker: 'WO', leave: null, holiday: null },
      '2026-11-02': { assignments: [{ id: 5, analyst_id: 10, project_id: 1, shift_template_id: 100, date: '2026-11-02', locked: false, source: 'solver', override_reason: null }], marker: null, leave: null, holiday: null },
      '2026-11-03': { assignments: [], marker: 'LEAVE', leave: { leave_id: 1, status: 'approved', partial: false, type: 'annual' }, holiday: null },
    } },
    { analyst_id: 11, employee_code: 'SYN-002', full_name: 'Synthetic Two', cells: {
      '2026-11-01': { assignments: [], marker: 'WO', leave: { leave_id: 2, status: 'pending', partial: false, type: 'sick' }, holiday: null },
      '2026-11-02': { assignments: [], marker: 'WO', leave: null, holiday: null },
      '2026-11-03': { assignments: [], marker: 'WO', leave: null, holiday: null },
    } },
  ],
  projects: [{ id: 1, code: 'SYN', name: 'Synthetic' }],
  shift_templates: [{ id: 100, project_id: 1, code: 'M', name: 'Morning', start_time: '06:00', end_time: '15:00', is_night: false, color: '#38bdf8', active: true }],
  holidays: [],
}

const validation: ValidationReport = {
  is_valid: false, error_count: 1, warning_count: 0, by_rule: { coverage: 1 }, coverage_percent: 90, metrics: {},
  violations: [
    { rule: 'min_rest', severity: 'error', message: 'SYN-001 rest too short', analyst_id: 10, project_id: 1, shift_id: 100, date: '2026-11-02' },
    { rule: 'coverage', severity: 'error', message: 'SYN/M on 2026-11-03 has 0 of 1', analyst_id: null, project_id: 1, shift_id: 100, date: '2026-11-03' },
  ],
}

describe('RosterMatrix', () => {
  it('renders shifts, markers, conflicts and pending leave', async () => {
    const onCellClick = vi.fn()
    render(<RosterMatrix roster={roster} validation={validation} editable filters={{ projectId: null, analystId: null, shiftCode: null }}
      onCellClick={onCellClick} onDrop={vi.fn()} />)
    expect(screen.getByText('SYN-001')).toBeInTheDocument()
    expect(screen.getByText('M')).toBeInTheDocument()
    expect(screen.getByText('LEAVE')).toBeInTheDocument()
    expect(screen.getByText('PL?')).toBeInTheDocument()
    const conflictCell = document.querySelector('[data-cell="10|2026-11-02"]')!
    expect(conflictCell.getAttribute('title')).toContain('rest too short')
    expect(screen.getByTitle(/0 of 1/)).toBeInTheDocument()
    await userEvent.click(document.querySelector('[data-cell="11|2026-11-03"]')!)
    expect(onCellClick).toHaveBeenCalledWith(11, '2026-11-03')
  })
  it('filters by analyst', () => {
    render(<RosterMatrix roster={roster} editable={false} filters={{ projectId: null, analystId: 11, shiftCode: null }}
      onCellClick={vi.fn()} onDrop={vi.fn()} />)
    expect(screen.queryByText('SYN-001')).not.toBeInTheDocument()
    expect(screen.getByText('SYN-002')).toBeInTheDocument()
  })
})

describe('small components', () => {
  it('MonthPicker moves across year boundaries', async () => {
    const onChange = vi.fn()
    render(<MonthPicker year={2026} month={12} onChange={onChange} />)
    await userEvent.click(screen.getByLabelText('Next month'))
    expect(onChange).toHaveBeenCalledWith(2027, 1)
  })
  it('ViolationList shows success state and truncates', () => {
    const { rerender } = render(<ViolationList violations={[]} />)
    expect(screen.getByText('No rule violations.')).toBeInTheDocument()
    rerender(<ViolationList violations={validation.violations} max={1} />)
    expect(screen.getByText(/and 1 more/)).toBeInTheDocument()
  })
  it('ShiftChip marks locked shifts', () => {
    render(<ShiftChip code="N" color="#6366f1" locked />)
    expect(screen.getByText(/N/).textContent).toContain('🔒')
  })
})
