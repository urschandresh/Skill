import { Lock, Trash2, Unlock } from 'lucide-react'
import { useState } from 'react'

import { NativeSelect, ShiftChip, ViolationList } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { slotOf } from '@/lib/roster'
import type { RosterDetail, RosterOp } from '@/types/api'

import type { PendingChange } from './useRosterEditor'

export function CellEditor({ roster, analystId, date, editable, busy, onApply, onClose }: {
  roster: RosterDetail
  analystId: number
  date: string
  editable: boolean
  busy: boolean
  onApply: (ops: RosterOp[], label: string) => void
  onClose: () => void
}) {
  const row = roster.rows.find((r) => r.analyst_id === analystId)
  const cell = row?.cells[date]
  const templates = roster.shift_templates.filter((t) => t.active && roster.project_ids.includes(t.project_id))
  const tplById = new Map(roster.shift_templates.map((t) => [t.id, t]))
  const projectCode = new Map(roster.projects.map((p) => [p.id, p.code]))
  const [choice, setChoice] = useState('')
  const [replace, setReplace] = useState(true)
  const existing = cell?.assignments ?? []
  const present = new Set(existing.map((a) => a.shift_template_id))
  const choices = templates.filter((t) => !present.has(t.id))

  const addOrReplace = () => {
    const t = tplById.get(Number(choice))
    if (!t) return
    const target = { analyst_id: analystId, project_id: t.project_id, shift_template_id: t.id, date }
    const movable = existing.filter((a) => !a.locked)
    if (replace && movable.length === 1) {
      const from = slotOf(movable[0])
      onApply([{ op: 'move', from_analyst_id: from.analyst_id, from_project_id: from.project_id,
        from_shift_template_id: from.shift_template_id, from_date: from.date, to_analyst_id: analystId,
        to_project_id: t.project_id, to_shift_template_id: t.id, to_date: date }], 'Change shift')
    } else {
      onApply([{ op: 'add', ...target }], 'Add shift')
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row?.employee_code} · {date}</DialogTitle>
          <DialogDescription>
            {row?.full_name}
            {cell?.leave && ` · ${cell.leave.status} ${cell.leave.partial ? 'partial-day ' : ''}leave (${cell.leave.type})`}
            {cell?.holiday && ` · Holiday: ${cell.holiday}`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {existing.length === 0 && <p className="text-sm text-muted-foreground">No shift ({cell?.marker ?? 'WO'}).</p>}
          {existing.map((a) => {
            const t = tplById.get(a.shift_template_id)
            const slot = slotOf(a)
            return (
              <div key={a.id} className="flex items-center justify-between rounded-lg border p-2">
                <div className="flex items-center gap-2 text-sm">
                  <ShiftChip code={t?.code ?? '?'} color={t?.color ?? '#94a3b8'} locked={a.locked}
                    label={roster.projects.length > 1 ? projectCode.get(a.project_id) : undefined} />
                  {t?.name} {t?.start_time}–{t?.end_time}
                  <span className="text-xs text-muted-foreground">({a.source})</span>
                </div>
                {editable && (
                  <div className="flex gap-1">
                    <Button size="icon-sm" variant="ghost" disabled={busy}
                      aria-label={a.locked ? 'Unlock assignment' : 'Lock assignment'}
                      onClick={() => onApply([{ op: a.locked ? 'unlock' : 'lock', ...slot }], a.locked ? 'Unlock' : 'Lock')}>
                      {a.locked ? <Unlock /> : <Lock />}
                    </Button>
                    <Button size="icon-sm" variant="ghost" disabled={busy || a.locked} aria-label="Remove assignment"
                      onClick={() => onApply([{ op: 'remove', ...slot }], 'Remove shift')}>
                      <Trash2 />
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
          {a11yOverrides(existing)}
        </div>
        {editable ? (
          <div className="grid gap-2 border-t pt-3">
            <Label htmlFor="cell-shift">{existing.length ? 'Change to / add shift' : 'Assign shift'}</Label>
            <NativeSelect id="cell-shift" value={choice} onChange={(e) => setChoice(e.target.value)}>
              <option value="">Choose shift…</option>
              {choices.map((t) => (
                <option key={t.id} value={t.id}>
                  {roster.projects.length > 1 ? `${projectCode.get(t.project_id)} ` : ''}{t.code} · {t.name} ({t.start_time}–{t.end_time})
                </option>
              ))}
            </NativeSelect>
            {existing.filter((a) => !a.locked).length === 1 && (
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
                Replace the existing shift (otherwise add a second one)
              </label>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>Close</Button>
              <Button disabled={!choice || busy} onClick={addOrReplace}>Check & apply</Button>
            </DialogFooter>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">This roster is read-only. Create a new draft version to edit.</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function a11yOverrides(existing: { id: number; override_reason: string | null }[]) {
  const reasons = existing.filter((a) => a.override_reason)
  if (!reasons.length) return null
  return (
    <ul className="text-xs text-amber-300">
      {reasons.map((a) => <li key={a.id}>Override recorded: {a.override_reason}</li>)}
    </ul>
  )
}

export function ChangeConfirmDialog({ pending, busy, onConfirm, onCancel }: {
  pending: PendingChange
  busy: boolean
  onConfirm: (reason: string) => void
  onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{pending.label}: this change breaks hard rules</DialogTitle>
          <DialogDescription>
            Nothing has been saved. Cancel to keep the roster as it is, or give a reason to save anyway.
            The reason is stored with the assignment and the roster stays flagged until fixed.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-64 overflow-auto"><ViolationList violations={pending.introduced} /></div>
        {pending.resolved.length > 0 && (
          <p className="text-xs text-emerald-400">It would also resolve {pending.resolved.length} existing violation(s).</p>
        )}
        <div className="grid gap-1.5">
          <Label htmlFor="override-reason">Override reason (at least 5 characters)</Label>
          <Textarea id="override-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Cancel change</Button>
          <Button variant="destructive" disabled={reason.trim().length < 5 || busy} onClick={() => onConfirm(reason.trim())}>
            Save with override
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
