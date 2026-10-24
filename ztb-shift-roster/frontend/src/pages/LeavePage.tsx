import dayGridPlugin from '@fullcalendar/daygrid'
import FullCalendar from '@fullcalendar/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Check, Pencil, Plus, Search, X } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState, ErrorAlert, Field, Loading, NativeSelect, PageHeader, StatusBadge, ViolationList } from '@/components/common'
import { JobProgress } from '@/components/JobProgress'
import { ChangeConfirmDialog } from '@/components/roster/CellEditor'
import type { PendingChange } from '@/components/roster/useRosterEditor'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { leaveSchema, type LeaveForm } from '@/lib/forms'
import { addDays } from '@/lib/roster'
import { useApiMutation } from '@/lib/useApiMutation'
import { api, errorMessage } from '@/services/api'
import { useAnalysts, useLeaves } from '@/services/queries'
import type { ChangeResult, Leave, RosterOp, Violation } from '@/types/api'

const STATUS_COLORS: Record<string, string> = { pending: '#f59e0b', approved: '#22c55e', rejected: '#f43f5e', cancelled: '#64748b' }

function LeaveDialog({ leave, onClose }: { leave: Leave | null; onClose: () => void }) {
  const { data: analysts = [] } = useAnalysts()
  const form = useForm<LeaveForm>({
    resolver: zodResolver(leaveSchema),
    defaultValues: {
      analyst_id: leave ? String(leave.analyst_id) : '', start_date: leave?.start_date ?? '', end_date: leave?.end_date ?? '',
      leave_type: (leave?.leave_type as LeaveForm['leave_type']) ?? 'annual', partial_day: leave?.partial_day ?? false,
      start_time: leave?.start_time ?? '', end_time: leave?.end_time ?? '', reason: leave?.reason ?? '',
    },
  })
  const save = useApiMutation((v: LeaveForm) => {
    const body = { ...v, analyst_id: Number(v.analyst_id), start_time: v.partial_day ? v.start_time : null,
      end_time: v.partial_day ? v.end_time : null }
    return leave ? api.put(`/leaves/${leave.id}`, body) : api.post('/leaves', body)
  }, { invalidate: [['leaves'], ['dashboard']], success: leave ? 'Leave updated' : 'Leave submitted' })
  const errors = form.formState.errors
  const partial = form.watch('partial_day')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{leave ? 'Edit leave' : 'Submit leave'}</DialogTitle>
          {leave?.status === 'approved' && <DialogDescription>Editing approved leave sends it back for approval.</DialogDescription>}
        </DialogHeader>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: onClose }))}>
          <Field label="Analyst" htmlFor="l-analyst" error={errors.analyst_id?.message}>
            <NativeSelect id="l-analyst" disabled={!!leave} {...form.register('analyst_id')}>
              <option value="">Choose…</option>
              {analysts.map((a) => <option key={a.id} value={a.id}>{a.employee_code} · {a.full_name}</option>)}
            </NativeSelect>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="From" htmlFor="l-start" error={errors.start_date?.message}>
              <Input id="l-start" type="date" {...form.register('start_date')} />
            </Field>
            <Field label="To" htmlFor="l-end" error={errors.end_date?.message}>
              <Input id="l-end" type="date" {...form.register('end_date')} />
            </Field>
          </div>
          <Field label="Type" htmlFor="l-type">
            <NativeSelect id="l-type" {...form.register('leave_type')}>
              {['annual', 'sick', 'casual', 'comp_off', 'unpaid', 'other'].map((t) => <option key={t} value={t}>{t}</option>)}
            </NativeSelect>
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={partial} onCheckedChange={(c) => form.setValue('partial_day', !!c)} /> Partial day
          </label>
          {partial && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="From time" htmlFor="l-st"><Input id="l-st" type="time" {...form.register('start_time')} /></Field>
              <Field label="To time" htmlFor="l-et" error={errors.end_time?.message}><Input id="l-et" type="time" {...form.register('end_time')} /></Field>
            </div>
          )}
          <Field label="Reason (optional)" htmlFor="l-reason"><Textarea id="l-reason" rows={2} {...form.register('reason')} /></Field>
          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface ImpactRoster {
  roster_id: number
  roster_name: string
  roster_status: string
  affected_assignments: { id: number; date: string; project_id: number; shift_template_id: number; locked: boolean }[]
  conflicts_if_kept: Violation[]
  consequences_if_removed: Violation[]
}
interface Replacement {
  roster_id: number
  date: string
  project_id: number
  shift_template_id: number
  fully_valid_options: number
  candidates: { analyst_id: number; employee_code: string; ok: boolean; new_violations: Violation[]; month_hours: number; month_nights: number }[]
}

function ImpactSheet({ leave, onClose }: { leave: Leave; onClose: () => void }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const impact = useQuery({ queryKey: ['impact', leave.id, leave.status], queryFn: () =>
    api.get<{ evaluated_as: string; rosters: ImpactRoster[]; no_roster: boolean }>(`/leaves/${leave.id}/impact`) })
  const repl = useQuery({ queryKey: ['replacements', leave.id, leave.status], queryFn: () =>
    api.get<{ shifts: Replacement[]; note: string }>(`/leaves/${leave.id}/replacements`) })
  const [runId, setRunId] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [margin, setMargin] = useState('2')

  const regenerate = async (rosterId: number, simulate: boolean) => {
    setError(null)
    try {
      const r = await api.post<{ run_id: string }>(`/leaves/${leave.id}/regenerate`,
        { roster_id: rosterId, simulate, margin_days: Number(margin) || 0, time_limit_seconds: 30 })
      setRunId(r.run_id)
    } catch (e) { setError(e) }
  }
  // Same rule as the roster editor: dry-run first, and a change that breaks hard rules needs a reason.
  const [pendingAssign, setPendingAssign] = useState<PendingChange | null>(null)
  const sendAssign = async (rosterId: number, ops: RosterOp[], reason: string | null) => {
    await api.post(`/rosters/${rosterId}/changes`, { ops, override_reason: reason })
    toast.success(reason ? 'Shift reassigned with override' : 'Shift reassigned')
    setPendingAssign(null)
    await qc.invalidateQueries()
  }
  const assign = async (rep: Replacement, analystId: number) => {
    const ops: RosterOp[] = [{ op: 'move', from_analyst_id: leave.analyst_id, from_project_id: rep.project_id,
      from_shift_template_id: rep.shift_template_id, from_date: rep.date, to_analyst_id: analystId,
      to_project_id: rep.project_id, to_shift_template_id: rep.shift_template_id, to_date: rep.date }]
    try {
      const dry = await api.post<ChangeResult>(`/rosters/${rep.roster_id}/changes`, { ops, dry_run: true })
      if (dry.introduced.length) {
        setPendingAssign({ ops, introduced: dry.introduced, resolved: dry.resolved, label: `Assign to roster ${rep.roster_id}`,
          rosterId: rep.roster_id } as PendingChange & { rosterId: number })
      } else {
        await sendAssign(rep.roster_id, ops, null)
      }
    } catch (e) { toast.error(errorMessage(e)) }
  }
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Leave impact · {leave.start_date}{leave.end_date !== leave.start_date ? ` → ${leave.end_date}` : ''}</SheetTitle>
          <SheetDescription>{impact.data?.evaluated_as ?? 'Evaluating…'}</SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6 text-sm">
          {impact.isLoading && <Loading />}
          <ErrorAlert error={impact.error} />
          {impact.data?.no_roster && <p className="text-muted-foreground">No roster exists for these dates yet; the leave will be respected when one is generated.</p>}
          {impact.data?.rosters.map((r) => (
            <div key={r.roster_id} className="space-y-2 rounded-lg border p-3" data-testid="impact-roster">
              <p className="font-medium">{r.roster_name} <StatusBadge status={r.roster_status} /></p>
              <p>{r.affected_assignments.length
                ? `${r.affected_assignments.length} assigned shift(s) clash with this leave: ${r.affected_assignments.map((a) => a.date).join(', ')}`
                : 'No assigned shifts clash with this leave.'}</p>
              {r.consequences_if_removed.length > 0 && (
                <div><p className="text-xs text-muted-foreground">If those shifts are dropped:</p><ViolationList violations={r.consequences_if_removed} max={8} /></div>
              )}
              {r.affected_assignments.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-xs">Window ± days <Input className="inline h-7 w-14" value={margin} onChange={(e) => setMargin(e.target.value)} aria-label="Margin days" /></label>
                  <Button size="sm" variant="outline" onClick={() => regenerate(r.roster_id, true)}>Simulate regeneration</Button>
                  <Button size="sm" disabled={leave.status !== 'approved'} onClick={() => regenerate(r.roster_id, false)}
                    title={leave.status !== 'approved' ? 'Approve the leave first' : ''}>Regenerate affected shifts</Button>
                </div>
              )}
            </div>
          ))}
          <ErrorAlert error={error} />
          {runId && <JobProgress runId={runId} onDone={(job) => {
            if (job.roster_id) { toast.success('New draft created'); navigate(`/rosters/${job.roster_id}`) }
          }} />}
          <div>
            <p className="mb-2 font-medium">Replacement suggestions</p>
            {repl.isLoading && <Loading />}
            {repl.data && !repl.data.shifts.length && <p className="text-muted-foreground">Nothing to replace.</p>}
            {repl.data?.shifts.map((s, i) => {
              const status = impact.data?.rosters.find((x) => x.roster_id === s.roster_id)?.roster_status
              return (
                <div key={i} className="mb-3 rounded-lg border p-3">
                  <p className="text-xs text-muted-foreground">{s.date} · {s.fully_valid_options} rule-clean option(s)</p>
                  <ul className="mt-1 space-y-1">
                    {s.candidates.map((c) => (
                      <li key={c.analyst_id} className="flex items-center justify-between gap-2">
                        <span className={c.ok ? 'text-emerald-300' : 'text-muted-foreground'}>
                          {c.employee_code} · {c.month_hours}h · {c.month_nights} nights
                          {!c.ok && ` · breaks: ${[...new Set(c.new_violations.map((v) => v.rule))].join(', ')}`}
                        </span>
                        <Button size="xs" variant="outline" disabled={status !== 'draft'}
                          title={status !== 'draft' ? 'Only draft rosters can be edited; regenerate or create a new version' : ''}
                          onClick={() => assign(s, c.analyst_id)}>Assign</Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
            {repl.data && <p className="text-xs text-muted-foreground">{repl.data.note}</p>}
          </div>
        </div>
      </SheetContent>
      {pendingAssign && (
        <ChangeConfirmDialog pending={pendingAssign} busy={false} onCancel={() => setPendingAssign(null)}
          onConfirm={(reason) => sendAssign((pendingAssign as PendingChange & { rosterId: number }).rosterId,
            pendingAssign.ops, reason).catch((e) => toast.error(errorMessage(e)))} />
      )}
    </Sheet>
  )
}

export function LeavePage() {
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const leaves = useLeaves({ status: status || undefined })
  const { data: analysts = [] } = useAnalysts()
  const [editing, setEditing] = useState<Leave | null | 'new'>(null)
  const [impact, setImpact] = useState<Leave | null>(null)
  const name = new Map(analysts.map((a) => [a.id, `${a.employee_code} · ${a.full_name}`]))
  const act = useApiMutation(({ id, action }: { id: number; action: string }) => api.post<Leave>(`/leaves/${id}/${action}`, { note: '' }),
    { invalidate: [['leaves'], ['dashboard'], ['impact']], success: (l) => `Leave ${l.status}` })
  const rows = (leaves.data ?? []).filter((l) => !search || (name.get(l.analyst_id) ?? '').toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      <PageHeader title="Leave" description="Submit, approve and assess leave. Pending leave can be simulated without touching published rosters."
        actions={<Button onClick={() => setEditing('new')}><Plus /> Submit leave</Button>} />
      <Tabs defaultValue="list">
        <TabsList><TabsTrigger value="list">Requests</TabsTrigger><TabsTrigger value="calendar">Leave calendar</TabsTrigger></TabsList>
        <TabsContent value="list">
          <div className="mb-3 flex flex-col gap-2 sm:flex-row">
            <div className="relative sm:w-72">
              <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" />
              <Input aria-label="Search leave" className="pl-8" placeholder="Search analyst" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <NativeSelect aria-label="Leave status filter" className="sm:w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {['pending', 'approved', 'rejected', 'cancelled'].map((s) => <option key={s} value={s}>{s}</option>)}
            </NativeSelect>
          </div>
          <ErrorAlert error={leaves.error} />
          {leaves.isLoading && <Loading />}
          {leaves.data && !rows.length && <EmptyState title="No leave requests" />}
          {rows.length > 0 && (
            <Card className="py-0">
              <CardContent className="overflow-x-auto p-0">
                <Table>
                  <TableHeader><TableRow><TableHead>Analyst</TableHead><TableHead>Dates</TableHead><TableHead>Type</TableHead>
                    <TableHead>Status</TableHead><TableHead className="hidden md:table-cell">Reason</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {rows.map((l) => (
                      <TableRow key={l.id}>
                        <TableCell>{name.get(l.analyst_id) ?? l.analyst_id}</TableCell>
                        <TableCell className="whitespace-nowrap">{l.start_date}{l.end_date !== l.start_date ? ` → ${l.end_date}` : ''}
                          {l.partial_day && <span className="text-xs text-muted-foreground"> {l.start_time}–{l.end_time}</span>}</TableCell>
                        <TableCell>{l.leave_type}</TableCell>
                        <TableCell><StatusBadge status={l.status} /></TableCell>
                        <TableCell className="hidden max-w-56 truncate text-xs md:table-cell">{l.reason}</TableCell>
                        <TableCell className="text-right whitespace-nowrap">
                          <Button size="xs" variant="outline" onClick={() => setImpact(l)}>Impact</Button>
                          {l.status === 'pending' && (
                            <>
                              <Button size="icon-xs" variant="ghost" aria-label="Approve" onClick={() => act.mutate({ id: l.id, action: 'approve' })}><Check /></Button>
                              <Button size="icon-xs" variant="ghost" aria-label="Reject" onClick={() => act.mutate({ id: l.id, action: 'reject' })}><X /></Button>
                            </>
                          )}
                          {(l.status === 'pending' || l.status === 'approved') && (
                            <>
                              <Button size="icon-xs" variant="ghost" aria-label="Edit" onClick={() => setEditing(l)}><Pencil /></Button>
                              <Button size="icon-xs" variant="ghost" aria-label="Cancel leave" onClick={() => act.mutate({ id: l.id, action: 'cancel' })}><Ban /></Button>
                            </>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="calendar">
          <div className="rounded-lg border bg-card p-2" data-testid="leave-calendar">
            <FullCalendar plugins={[dayGridPlugin]} initialView="dayGridMonth" timeZone="UTC" firstDay={1} height="auto"
              headerToolbar={{ left: 'prev,next today', center: 'title', right: '' }}
              events={(leaves.data ?? []).filter((l) => l.status !== 'cancelled' && l.status !== 'rejected').map((l) => ({
                id: String(l.id), title: `${analysts.find((a) => a.id === l.analyst_id)?.employee_code ?? l.analyst_id} · ${l.leave_type}${l.status === 'pending' ? ' (pending)' : ''}`,
                start: l.start_date, end: addDays(l.end_date, 1), allDay: true,
                backgroundColor: STATUS_COLORS[l.status], borderColor: STATUS_COLORS[l.status],
              }))}
              eventClick={(info) => { const l = leaves.data?.find((x) => String(x.id) === info.event.id); if (l) setImpact(l) }} />
          </div>
        </TabsContent>
      </Tabs>
      {editing && <LeaveDialog leave={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {impact && <ImpactSheet leave={impact} onClose={() => setImpact(null)} />}
    </div>
  )
}
