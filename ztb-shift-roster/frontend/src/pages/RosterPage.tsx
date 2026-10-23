import { useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Download, RefreshCw, Redo2, Send, Trash2, Undo2, Wand2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { ErrorAlert, InfoAlert, Loading, NativeSelect, PageHeader, StatusBadge, ViolationList } from '@/components/common'
import { JobProgress } from '@/components/JobProgress'
import { CellEditor, ChangeConfirmDialog } from '@/components/roster/CellEditor'
import { RosterCalendar } from '@/components/roster/RosterCalendar'
import { RosterMatrix, ShiftCoverageView } from '@/components/roster/RosterMatrix'
import { useRosterEditor } from '@/components/roster/useRosterEditor'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { addDays, moveOp, slotOf } from '@/lib/roster'
import { useApiMutation } from '@/lib/useApiMutation'
import { ApiError, api, downloadFile, errorMessage } from '@/services/api'
import { keys, useRoster, useRosters, useValidation } from '@/services/queries'
import type { RosterSummary, SlotRef, ValidationReport } from '@/types/api'

function PublishDialog({ rosterId, validation, onClose }: { rosterId: number; validation?: ValidationReport; onClose: () => void }) {
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const invalid = validation && !validation.is_valid
  const publish = async () => {
    try {
      await api.post(`/rosters/${rosterId}/publish`, { override_reason: invalid ? reason : null })
      await qc.invalidateQueries()
      toast.success('Roster published')
      onClose()
    } catch (e) {
      setError(e)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish roster</DialogTitle>
          <DialogDescription>
            Publishing makes this the official roster for the month. Any previously published version for the same
            projects is archived. Published rosters are read-only.
          </DialogDescription>
        </DialogHeader>
        {invalid ? (
          <div className="space-y-2">
            <p className="text-sm text-rose-300">This roster has {validation.error_count} rule violation(s).</p>
            <div className="max-h-48 overflow-auto"><ViolationList violations={validation.violations.filter((v) => v.severity === 'error')} max={20} /></div>
            <Label htmlFor="pub-reason">Reason for publishing anyway</Label>
            <Textarea id="pub-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        ) : <p className="text-sm text-emerald-400">Independent validation passed.</p>}
        <ErrorAlert error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={publish} disabled={!!invalid && reason.trim().length < 5}><Send /> Publish</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RegenerateDialog({ rosterId, start, end, onClose }: { rosterId: number; start: string; end: string; onClose: () => void }) {
  const navigate = useNavigate()
  const [from, setFrom] = useState(start)
  const [to, setTo] = useState(end)
  const [limit, setLimit] = useState('30')
  const [simulate, setSimulate] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const go = async () => {
    setError(null)
    try {
      const whole = from === start && to === end
      const r = await api.post<{ run_id: string }>(`/rosters/${rosterId}/regenerate`, {
        window_start: whole ? null : from, window_end: whole ? null : to,
        time_limit_seconds: Number(limit) || 30, simulate })
      setRunId(r.run_id)
    } catch (e) {
      setError(e)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Regenerate with minimum disruption</DialogTitle>
          <DialogDescription>
            Assignments outside the window and all locked assignments are kept. The solver changes as little as possible
            inside the window. The result is a new draft version; this roster is not modified.
          </DialogDescription>
        </DialogHeader>
        {!runId ? (
          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label htmlFor="rg-from">From</Label>
                <Input id="rg-from" type="date" min={start} max={end} value={from} onChange={(e) => setFrom(e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="rg-to">To</Label>
                <Input id="rg-to" type="date" min={start} max={end} value={to} onChange={(e) => setTo(e.target.value)} /></div>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="rg-limit">Solver time limit (seconds)</Label>
              <Input id="rg-limit" inputMode="numeric" value={limit} onChange={(e) => setLimit(e.target.value)} /></div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={simulate} onChange={(e) => setSimulate(e.target.checked)} />
              Simulation only (show what would change, save nothing)
            </label>
            <ErrorAlert error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button onClick={go}><Wand2 /> Start</Button>
            </DialogFooter>
          </div>
        ) : (
          <JobProgress runId={runId} onDone={(job) => {
            if (job.roster_id) {
              toast.success('New draft version created')
              navigate(`/rosters/${job.roster_id}`)
              onClose()
            }
          }} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function VersionPicker({ current, versions }: { current: number; versions: RosterSummary[] }) {
  const navigate = useNavigate()
  if (versions.length < 2) return null
  return (
    <NativeSelect aria-label="Version" className="w-56" value={current} onChange={(e) => navigate(`/rosters/${e.target.value}`)}>
      {versions.map((v) => <option key={v.id} value={v.id}>v{v.version} · {v.status} · {v.name}</option>)}
    </NativeSelect>
  )
}

export function RosterPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const roster = useRoster(id)
  const validation = useValidation(id)
  const versions = useRosters(roster.data ? { year: roster.data.year, month: roster.data.month } : { year: 0 })
  const editor = useRosterEditor(id)
  const [cell, setCell] = useState<{ analystId: number; date: string } | null>(null)
  const [filters, setFilters] = useState<{ projectId: number | null; analystId: number | null; shiftCode: string | null }>(
    { projectId: null, analystId: null, shiftCode: null })
  const [dialog, setDialog] = useState<'publish' | 'regenerate' | null>(null)
  const clone = useApiMutation(() => api.post<RosterSummary>(`/rosters/${id}/clone`), {
    invalidate: [['rosters']], success: 'New draft version created' })
  const del = useApiMutation(() => api.del(`/rosters/${id}`), { invalidate: [['rosters'], ['dashboard']], success: 'Roster deleted' })

  const r = roster.data
  const editable = r?.status === 'draft'
  const { undo, redo, canUndo, canRedo, resetHistory } = editor

  useEffect(() => { resetHistory() }, [id, resetHistory])
  useEffect(() => {
    if (!editable) return
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [role="dialog"]')) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey && canUndo) { e.preventDefault(); undo() }
      if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey)) && canRedo) {
        e.preventDefault(); redo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editable, undo, redo, canUndo, canRedo])

  if (roster.isLoading) return <Loading />
  if (roster.error) return <ErrorAlert error={roster.error} />
  if (!r) return null

  const onDrop = (from: SlotRef, toAnalyst: number, toDate: string) => {
    if (from.analyst_id === toAnalyst && from.date === toDate) return
    void editor.apply([moveOp(from, { ...from, analyst_id: toAnalyst, date: toDate })], 'Move shift')
  }
  const exportXlsx = async () => {
    try {
      await downloadFile(`/rosters/${id}/export.xlsx`, `roster-${r.year}-${String(r.month).padStart(2, '0')}.xlsx`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  const shiftCodes = [...new Set(r.shift_templates.map((t) => t.code))]
  const v = validation.data

  return (
    <div>
      <PageHeader
        title={r.name}
        description={`${r.projects.map((p) => p.code).join(', ')} · ${r.assignment_count} assignments · ${r.locked_count} locked`}
        actions={
          <>
            <VersionPicker current={id} versions={versions.data ?? []} />
            {editable && (
              <>
                <Button variant="outline" size="sm" onClick={undo} disabled={!canUndo || editor.busy} aria-label="Undo"><Undo2 /> Undo</Button>
                <Button variant="outline" size="sm" onClick={redo} disabled={!canRedo || editor.busy} aria-label="Redo"><Redo2 /> Redo</Button>
              </>
            )}
            <Button variant="outline" size="sm" onClick={() => validation.refetch()}><RefreshCw /> Validate</Button>
            <Button variant="outline" size="sm" onClick={exportXlsx}><Download /> Export XLSX</Button>
            {r.status !== 'historical' && (
              <Button variant="outline" size="sm" onClick={() => setDialog('regenerate')}><Wand2 /> Regenerate</Button>
            )}
            {(r.status === 'published' || r.status === 'archived' || r.status === 'historical') && (
              <Button size="sm" onClick={() => clone.mutate(undefined, { onSuccess: (c) => navigate(`/rosters/${c.id}`) })}>
                <CopyPlus /> New draft version
              </Button>
            )}
            {editable && <Button size="sm" onClick={() => setDialog('publish')}><Send /> Publish</Button>}
            {(editable || r.status === 'historical') && (
              <Button size="sm" variant="destructive" aria-label="Delete roster"
                onClick={() => window.confirm('Delete this roster version?') && del.mutate(undefined, { onSuccess: () => navigate('/rosters') })}>
                <Trash2 />
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge status={r.status} />
        <StatusBadge status={r.solver_status} />
        {r.parent_roster_id && <Link className="text-primary hover:underline" to={`/rosters/${r.parent_roster_id}`}>parent version</Link>}
        {v && (
          <span className={v.is_valid ? 'text-emerald-400' : 'text-rose-300'} data-testid="validation-summary">
            {v.is_valid ? 'Valid' : `${v.error_count} violation(s)`} · coverage {v.coverage_percent}%
          </span>
        )}
        {editor.busy && <span className="text-muted-foreground">Checking change…</span>}
      </div>
      {!editable && (
        <InfoAlert title={`This roster is ${r.status} and read-only`}>
          Create a new draft version to make changes. Drafts are validated on every edit.
        </InfoAlert>
      )}
      {r.notes && <p className="mb-3 whitespace-pre-line text-xs text-amber-300">{r.notes}</p>}

      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3 lg:w-2/3">
        <NativeSelect aria-label="Project filter" value={filters.projectId ?? ''}
          onChange={(e) => setFilters({ ...filters, projectId: e.target.value ? Number(e.target.value) : null })}>
          <option value="">All projects</option>
          {r.projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Analyst filter" value={filters.analystId ?? ''}
          onChange={(e) => setFilters({ ...filters, analystId: e.target.value ? Number(e.target.value) : null })}>
          <option value="">All analysts</option>
          {r.rows.map((row) => <option key={row.analyst_id} value={row.analyst_id}>{row.employee_code} · {row.full_name}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Shift filter" value={filters.shiftCode ?? ''}
          onChange={(e) => setFilters({ ...filters, shiftCode: e.target.value || null })}>
          <option value="">All shifts</option>
          {shiftCodes.map((c) => <option key={c} value={c}>{c}</option>)}
        </NativeSelect>
      </div>

      <Tabs defaultValue="matrix">
        <TabsList className="flex-wrap">
          <TabsTrigger value="matrix">Monthly matrix</TabsTrigger>
          <TabsTrigger value="shifts">Shift view</TabsTrigger>
          <TabsTrigger value="week">Week</TabsTrigger>
          <TabsTrigger value="month">Month calendar</TabsTrigger>
        </TabsList>
        <TabsContent value="matrix">
          <p className="mb-2 text-xs text-muted-foreground">
            {editable ? 'Drag a shift to another analyst or day, or click a cell to edit. Ctrl+Z / Ctrl+Y undo and redo. '
              : 'Click a cell for details. '}
            Red cells break a hard rule; red column headers are understaffed days; dashed amber = pending leave.
          </p>
          <RosterMatrix roster={r} validation={v} editable={editable} filters={filters}
            onCellClick={(analystId, date) => setCell({ analystId, date })} onDrop={onDrop} />
        </TabsContent>
        <TabsContent value="shifts">
          <ShiftCoverageView roster={r} validation={v} filters={filters} />
        </TabsContent>
        <TabsContent value="week">
          <RosterCalendar roster={r} view="timeGridWeek" editable={editable} filters={filters}
            onMove={(a, delta) => void editor.apply([moveOp(slotOf(a), { ...slotOf(a), date: addDays(a.date, delta) })], 'Move shift')}
            onSelect={(analystId, date) => setCell({ analystId, date })} />
        </TabsContent>
        <TabsContent value="month">
          <RosterCalendar roster={r} view="dayGridMonth" editable={editable} filters={filters}
            onMove={(a, delta) => void editor.apply([moveOp(slotOf(a), { ...slotOf(a), date: addDays(a.date, delta) })], 'Move shift')}
            onSelect={(analystId, date) => setCell({ analystId, date })} />
        </TabsContent>
      </Tabs>

      <Card className="mt-6">
        <CardHeader><CardTitle>Validation report</CardTitle></CardHeader>
        <CardContent>
          {validation.isLoading && <Loading label="Validating…" />}
          {validation.error instanceof ApiError && <ErrorAlert error={validation.error} />}
          {v && (
            <>
              <p className="mb-2 text-xs text-muted-foreground">
                Checked by the independent validator against current leave, settings and locks.
                {Object.entries(v.by_rule).map(([rule, n]) => ` ${rule}: ${n}`).join(' ·')}
              </p>
              <ViolationList violations={v.violations} max={100} />
            </>
          )}
        </CardContent>
      </Card>

      {cell && (
        <CellEditor roster={r} analystId={cell.analystId} date={cell.date} editable={editable} busy={editor.busy}
          onApply={(ops, label) => { void editor.apply(ops, label); setCell(null) }} onClose={() => setCell(null)} />
      )}
      {editor.pending && (
        <ChangeConfirmDialog pending={editor.pending} busy={editor.busy}
          onConfirm={(reason) => editor.confirmPending(reason)} onCancel={editor.dismissPending} />
      )}
      {dialog === 'publish' && <PublishDialog rosterId={id} validation={v} onClose={() => { setDialog(null); void qc.invalidateQueries({ queryKey: keys.roster(id) }) }} />}
      {dialog === 'regenerate' && <RegenerateDialog rosterId={id} start={r.start_date} end={r.end_date} onClose={() => setDialog(null)} />}
    </div>
  )
}
