import { useState } from 'react'

import { ShiftChip } from '@/components/common'
import { addDays, coverageIssuesByDate, isWeekend, parseISODate, slotOf, violationIndex, WEEKDAYS, weekdayIndex } from '@/lib/roster'
import { cn } from '@/lib/utils'
import type { Assignment, RosterDetail, ShiftTemplate, SlotRef, ValidationReport } from '@/types/api'

const MARKER_STYLE: Record<string, string> = {
  WO: 'text-muted-foreground/60',
  LEAVE: 'bg-amber-500/20 text-amber-300 font-semibold',
  H: 'bg-violet-500/20 text-violet-300 font-semibold',
}

export interface MatrixProps {
  roster: RosterDetail
  validation?: ValidationReport
  editable: boolean
  filters: { projectId: number | null; analystId: number | null; shiftCode: string | null }
  onCellClick: (analystId: number, date: string) => void
  onDrop: (from: SlotRef, toAnalyst: number, toDate: string) => void
}

/** Analyst x date grid with drag-and-drop, leave/week-off markers and conflict highlighting. */
export function RosterMatrix({ roster, validation, editable, filters, onCellClick, onDrop }: MatrixProps) {
  const [dragOver, setDragOver] = useState<string | null>(null)
  const dates: string[] = []
  for (let d = roster.start_date; d <= roster.end_date; d = addDays(d, 1)) dates.push(d)
  const templates = new Map<number, ShiftTemplate>(roster.shift_templates.map((t) => [t.id, t]))
  const projectCode = new Map(roster.projects.map((p) => [p.id, p.code]))
  const multiProject = roster.projects.length > 1
  const conflicts = violationIndex(validation?.violations ?? [])
  const coverage = coverageIssuesByDate(validation?.violations ?? [])
  const visible = (a: Assignment) =>
    (filters.projectId == null || a.project_id === filters.projectId) &&
    (filters.shiftCode == null || templates.get(a.shift_template_id)?.code === filters.shiftCode)
  const rows = roster.rows.filter((r) => filters.analystId == null || r.analyst_id === filters.analystId)
  const metrics = validation?.metrics ?? {}

  return (
    <div className="overflow-auto rounded-lg border" style={{ maxHeight: '70vh' }}>
      <table className="roster-grid w-max border-collapse text-xs" data-testid="roster-matrix">
        <thead className="sticky top-0 z-20 bg-card">
          <tr>
            <th className="sticky left-0 z-30 min-w-40 border-r border-b bg-card px-2 py-1 text-left">Analyst</th>
            {dates.map((d) => {
              const issues = coverage.get(d)
              return (
                <th key={d} title={issues?.map((v) => v.message).join('\n')}
                  className={cn('min-w-11 border-b px-1 py-1 text-center font-normal',
                    isWeekend(d) && 'bg-muted/60', issues && 'border-t-2 border-t-rose-500 text-rose-300')}>
                  <div className="font-semibold">{parseISODate(d).getUTCDate()}</div>
                  <div className="text-[10px] text-muted-foreground">{WEEKDAYS[weekdayIndex(d)].slice(0, 2)}</div>
                </th>
              )
            })}
            <th className="border-b border-l px-2 text-right font-normal">Shifts</th>
            <th className="border-b px-2 text-right font-normal">Nights</th>
            <th className="border-b px-2 text-right font-normal">Hours</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const m = metrics[String(row.analyst_id)]
            return (
              <tr key={row.analyst_id}>
                <th scope="row" className="sticky left-0 z-10 border-r border-b bg-card px-2 py-1 text-left font-normal">
                  <div className="font-medium">{row.employee_code}</div>
                  <div className="max-w-36 truncate text-[10px] text-muted-foreground">{row.full_name}</div>
                </th>
                {dates.map((d) => {
                  const cell = row.cells[d]
                  const key = `${row.analyst_id}|${d}`
                  const errs = conflicts.get(key)
                  const items = cell?.assignments.filter(visible) ?? []
                  const hidden = (cell?.assignments.length ?? 0) - items.length
                  const pendingLeave = cell?.leave?.status === 'pending'
                  const partialLeave = cell?.leave?.status === 'approved' && cell.leave.partial
                  return (
                    <td
                      key={d}
                      data-cell={key}
                      title={[...(errs?.map((v) => v.message) ?? []), pendingLeave ? 'Pending leave request' : '',
                        partialLeave ? 'Partial-day leave' : '', cell?.holiday ? `Holiday: ${cell.holiday}` : '']
                        .filter(Boolean).join('\n') || undefined}
                      onClick={() => onCellClick(row.analyst_id, d)}
                      onDragOver={(e) => { if (editable) { e.preventDefault(); setDragOver(key) } }}
                      onDragLeave={() => setDragOver((k) => (k === key ? null : k))}
                      onDrop={(e) => {
                        e.preventDefault()
                        setDragOver(null)
                        const raw = e.dataTransfer.getData('application/x-ztb-slot')
                        if (raw && editable) onDrop(JSON.parse(raw) as SlotRef, row.analyst_id, d)
                      }}
                      className={cn('h-10 cursor-pointer border-b px-0.5 text-center align-middle hover:bg-accent/40',
                        isWeekend(d) && 'bg-muted/30',
                        errs && 'bg-rose-500/15 outline outline-1 -outline-offset-1 outline-rose-500',
                        dragOver === key && 'bg-primary/30',
                        pendingLeave && 'outline-dashed outline-1 -outline-offset-2 outline-amber-400')}
                    >
                      <div className="flex flex-col items-center gap-0.5">
                        {items.map((a) => {
                          const t = templates.get(a.shift_template_id)
                          return (
                            <span key={a.id} draggable={editable && !a.locked}
                              onDragStart={(e) => {
                                e.dataTransfer.setData('application/x-ztb-slot', JSON.stringify(slotOf(a)))
                                e.dataTransfer.effectAllowed = 'move'
                              }}
                              onClick={(e) => { e.stopPropagation(); onCellClick(row.analyst_id, d) }}>
                              <ShiftChip code={t?.code ?? '?'} color={t?.color ?? '#94a3b8'} locked={a.locked}
                                label={multiProject ? projectCode.get(a.project_id) : undefined}
                                title={`${t?.name ?? ''} ${t?.start_time}–${t?.end_time}${a.override_reason ? `\nOverride: ${a.override_reason}` : ''}`} />
                            </span>
                          )
                        })}
                        {!items.length && hidden === 0 && cell?.marker && (
                          <span className={cn('rounded px-1 text-[10px]', MARKER_STYLE[cell.marker] ?? '')}>{cell.marker}</span>
                        )}
                        {hidden > 0 && !items.length && <span className="text-[10px] text-muted-foreground">·</span>}
                        {(pendingLeave || partialLeave) && (
                          <span className="text-[9px] text-amber-300">{pendingLeave ? 'PL?' : '½L'}</span>
                        )}
                      </div>
                    </td>
                  )
                })}
                <td className="border-b border-l px-2 text-right tabular-nums">{m?.shifts ?? ''}</td>
                <td className="border-b px-2 text-right tabular-nums">{m?.nights ?? ''}</td>
                <td className="border-b px-2 text-right tabular-nums">{m?.hours ?? ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Shift x date coverage grid: assigned vs. required, with analyst codes. */
export function ShiftCoverageView({ roster, validation, filters }: {
  roster: RosterDetail
  validation?: ValidationReport
  filters: MatrixProps['filters']
}) {
  const dates: string[] = []
  for (let d = roster.start_date; d <= roster.end_date; d = addDays(d, 1)) dates.push(d)
  const codeOf = new Map(roster.rows.map((r) => [r.analyst_id, r.employee_code]))
  const projectCode = new Map(roster.projects.map((p) => [p.id, p.code]))
  const req = new Map((validation?.coverage ?? []).map((c) => [`${c.project_id}|${c.shift_id}|${c.date}`, c]))
  const templates = roster.shift_templates
    .filter((t) => roster.project_ids.includes(t.project_id))
    .filter((t) => filters.projectId == null || t.project_id === filters.projectId)
    .filter((t) => filters.shiftCode == null || t.code === filters.shiftCode)
    .sort((a, b) => a.project_id - b.project_id || a.start_time.localeCompare(b.start_time))
  return (
    <div className="overflow-auto rounded-lg border" style={{ maxHeight: '70vh' }}>
      <table className="roster-grid w-max border-collapse text-xs" data-testid="shift-view">
        <thead className="sticky top-0 z-20 bg-card">
          <tr>
            <th className="sticky left-0 z-30 min-w-28 border-r border-b bg-card px-2 py-1 text-left">Shift</th>
            {dates.map((d) => (
              <th key={d} className={cn('min-w-14 border-b px-1 py-1 font-normal', isWeekend(d) && 'bg-muted/60')}>
                <div className="font-semibold">{parseISODate(d).getUTCDate()}</div>
                <div className="text-[10px] text-muted-foreground">{WEEKDAYS[weekdayIndex(d)].slice(0, 2)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {templates.map((t) => (
            <tr key={t.id}>
              <th scope="row" className="sticky left-0 z-10 border-r border-b bg-card px-2 py-1 text-left font-normal">
                <ShiftChip code={t.code} color={t.color} label={projectCode.get(t.project_id)} />
                <div className="text-[10px] text-muted-foreground">{t.start_time}–{t.end_time}</div>
              </th>
              {dates.map((d) => {
                const who = roster.assignments.filter((a) => a.shift_template_id === t.id && a.date === d &&
                  (filters.analystId == null || a.analyst_id === filters.analystId))
                const c = req.get(`${t.project_id}|${t.id}|${d}`)
                const short = c && c.assigned < c.required
                return (
                  <td key={d} className={cn('border-b px-1 py-1 align-top', isWeekend(d) && 'bg-muted/30',
                    short && 'bg-rose-500/15 outline outline-1 -outline-offset-1 outline-rose-500')}>
                    <div className={cn('text-[10px] font-semibold', short ? 'text-rose-300' : 'text-muted-foreground')}>
                      {c ? `${c.assigned}/${c.required}` : who.length}
                    </div>
                    {who.map((a) => <div key={a.id} className="truncate">{codeOf.get(a.analyst_id)}{a.locked ? ' 🔒' : ''}</div>)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
