import { useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseBackup, Download, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ErrorAlert, Field, InfoAlert, Loading, NativeSelect, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { splitCodes } from '@/lib/forms'
import { WEEKDAYS } from '@/lib/roster'
import { useApiMutation } from '@/lib/useApiMutation'
import { api, downloadFile, errorMessage } from '@/services/api'
import { keys, useAnalysts, useAvailability, useHolidays, useMappings, usePolicies, useProjects, useSkills } from '@/services/queries'
import type { Policy } from '@/types/api'

type PolicyDraft = Omit<Policy, 'id'>

const NUMBER_FIELDS: [keyof PolicyDraft, string][] = [
  ['working_days_per_week', 'Working days / week'], ['max_hours_per_week', 'Max hours / week'],
  ['max_consecutive_work_days', 'Max consecutive days'], ['max_consecutive_nights', 'Max consecutive nights'],
  ['min_rest_hours', 'Min rest (hours)'], ['solver_time_limit_seconds', 'Solver time limit (s)'],
]

function PolicyDialog({ policy, onClose }: { policy: Policy | null; onClose: () => void }) {
  const base = policy ?? {
    name: '', is_default: false, working_days_per_week: 5, week_start_day: 0, weekly_mode: 'exact' as const,
    max_hours_per_week: 48, max_consecutive_work_days: 6, max_consecutive_nights: 5, min_rest_hours: 11,
    one_shift_per_day: true, leave_counts_as_working_day: true, solver_time_limit_seconds: 30,
    weights: { fair_nights: 10, fair_weekends: 8, balanced_hours: 5, preferences: 2, shift_changes: 3, disruption: 20 },
  }
  const [d, setD] = useState<PolicyDraft>({ ...base })
  const save = useApiMutation(() => {
    const { ...body } = d as PolicyDraft & { id?: number }
    delete body.id
    return policy ? api.put(`/policies/${policy.id}`, body) : api.post('/policies', body)
  }, { invalidate: [keys.policies], success: 'Policy saved' })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle>{policy ? `Edit ${policy.name}` : 'New policy'}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <Field label="Name" htmlFor="pol-name"><Input id="pol-name" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {NUMBER_FIELDS.map(([k, label]) => (
              <Field key={k} label={label} htmlFor={`pol-${k}`}>
                <Input id={`pol-${k}`} inputMode="numeric" value={String(d[k])} onChange={(e) => setD({ ...d, [k]: Number(e.target.value) || 0 })} />
              </Field>
            ))}
            <Field label="Week starts" htmlFor="pol-ws">
              <NativeSelect id="pol-ws" value={d.week_start_day} onChange={(e) => setD({ ...d, week_start_day: Number(e.target.value) })}>
                {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Weekly rule" htmlFor="pol-mode">
              <NativeSelect id="pol-mode" value={d.weekly_mode} onChange={(e) => setD({ ...d, weekly_mode: e.target.value as 'exact' | 'max' })}>
                <option value="exact">Exactly N days</option><option value="max">At most N days</option>
              </NativeSelect>
            </Field>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><Checkbox checked={d.one_shift_per_day} onCheckedChange={(c) => setD({ ...d, one_shift_per_day: !!c })} /> One shift per day</label>
            <label className="flex items-center gap-2"><Checkbox checked={d.leave_counts_as_working_day} onCheckedChange={(c) => setD({ ...d, leave_counts_as_working_day: !!c })} /> Leave counts as a working day</label>
            <label className="flex items-center gap-2"><Checkbox checked={d.is_default} onCheckedChange={(c) => setD({ ...d, is_default: !!c })} /> Default policy</label>
          </div>
          <p className="text-sm font-medium">Objective weights</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {(Object.keys(d.weights) as (keyof Policy['weights'])[]).map((k) => (
              <Field key={k} label={k.replace('_', ' ')} htmlFor={`pw-${k}`}>
                <Input id={`pw-${k}`} inputMode="numeric" value={String(d.weights[k])}
                  onChange={(e) => setD({ ...d, weights: { ...d.weights, [k]: Number(e.target.value) || 0 } })} />
              </Field>
            ))}
          </div>
          <ErrorAlert error={save.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate(undefined, { onSuccess: onClose })} disabled={save.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PoliciesTab() {
  const { data, isLoading } = usePolicies()
  const [editing, setEditing] = useState<Policy | null | 'new'>(null)
  const del = useApiMutation((id: number) => api.del(`/policies/${id}`), { invalidate: [keys.policies], success: 'Policy deleted' })
  return (
    <Card>
      <CardHeader><CardTitle>Scheduling policies</CardTitle>
        <CardDescription>Hard rules and objective weights. The default policy is pre-selected in the generator.</CardDescription></CardHeader>
      <CardContent>
        {isLoading && <Loading />}
        <Table>
          <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Week</TableHead><TableHead>Rest</TableHead>
            <TableHead>Max consecutive</TableHead><TableHead>Max h/week</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {data?.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.name} {p.is_default && <Badge>default</Badge>}</TableCell>
                <TableCell>{p.weekly_mode === 'exact' ? 'exactly' : 'up to'} {p.working_days_per_week} days</TableCell>
                <TableCell>{p.min_rest_hours} h</TableCell>
                <TableCell>{p.max_consecutive_work_days} days / {p.max_consecutive_nights} nights</TableCell>
                <TableCell>{p.max_hours_per_week}</TableCell>
                <TableCell className="text-right">
                  <Button size="icon-xs" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}><Pencil /></Button>
                  {!p.is_default && <Button size="icon-xs" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => del.mutate(p.id)}><Trash2 /></Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Button className="mt-3" size="sm" variant="outline" onClick={() => setEditing('new')}><Plus /> Policy</Button>
        {editing && <PolicyDialog policy={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      </CardContent>
    </Card>
  )
}

function SimpleListTab() {
  const skills = useSkills()
  const holidays = useHolidays()
  const projects = useProjects()
  const [skill, setSkill] = useState('')
  const [hol, setHol] = useState({ date: '', name: '', project_id: '', blocks_work: false })
  const addSkill = useApiMutation(() => api.post('/skills', { name: skill }), { invalidate: [keys.skills], success: 'Skill added' })
  const delSkill = useApiMutation((id: number) => api.del(`/skills/${id}`), { invalidate: [keys.skills] })
  const addHol = useApiMutation(() => api.post('/holidays', { ...hol, project_id: hol.project_id ? Number(hol.project_id) : null }),
    { invalidate: [keys.holidays], success: 'Holiday added' })
  const delHol = useApiMutation((id: number) => api.del(`/holidays/${id}`), { invalidate: [keys.holidays] })
  const pcode = new Map((projects.data ?? []).map((p) => [p.id, p.code]))
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Skills</CardTitle><CardDescription>Required by projects or shifts; held by analysts.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {skills.data?.map((s) => (
              <Badge key={s.id} variant="secondary" className="gap-1">{s.name}
                <button aria-label={`Delete skill ${s.name}`} onClick={() => delSkill.mutate(s.id)}><Trash2 className="size-3" /></button>
              </Badge>
            ))}
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (skill.trim()) addSkill.mutate(undefined, { onSuccess: () => setSkill('') }) }}>
            <Input aria-label="New skill" placeholder="e.g. SIEM, EDR, Cloud" value={skill} onChange={(e) => setSkill(e.target.value)} />
            <Button type="submit" variant="outline"><Plus /> Add</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Holidays</CardTitle>
          <CardDescription>Shown as H. SOC coverage normally continues; tick "blocks work" only if nobody works that day.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <ul className="space-y-1 text-sm">
            {holidays.data?.map((h) => (
              <li key={h.id} className="flex items-center justify-between">
                <span>{h.date} · {h.name}{h.project_id ? ` (${pcode.get(h.project_id)})` : ''}{h.blocks_work ? ' · blocks work' : ''}</span>
                <Button size="icon-xs" variant="ghost" aria-label="Delete holiday" onClick={() => delHol.mutate(h.id)}><Trash2 /></Button>
              </li>
            ))}
          </ul>
          <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); addHol.mutate(undefined) }}>
            <Input type="date" aria-label="Holiday date" value={hol.date} onChange={(e) => setHol({ ...hol, date: e.target.value })} />
            <Input aria-label="Holiday name" placeholder="Name" value={hol.name} onChange={(e) => setHol({ ...hol, name: e.target.value })} />
            <NativeSelect aria-label="Holiday project" value={hol.project_id} onChange={(e) => setHol({ ...hol, project_id: e.target.value })}>
              <option value="">All projects</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </NativeSelect>
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={hol.blocks_work} onCheckedChange={(c) => setHol({ ...hol, blocks_work: !!c })} /> Blocks work</label>
            <Button type="submit" variant="outline" className="sm:col-span-2"><Plus /> Add holiday</Button>
          </form>
          <ErrorAlert error={addHol.error} />
        </CardContent>
      </Card>
    </div>
  )
}

function AvailabilityTab() {
  const { data } = useAvailability()
  const { data: analysts = [] } = useAnalysts()
  const [f, setF] = useState({ analyst_id: '', date: '', kind: 'unavailable', codes: '', note: '' })
  const add = useApiMutation(() => api.post('/availability', { analyst_id: Number(f.analyst_id), date: f.date, kind: f.kind,
    shift_codes: splitCodes(f.codes), note: f.note }), { invalidate: [keys.availability], success: 'Exception added' })
  const del = useApiMutation((id: number) => api.del(`/availability/${id}`), { invalidate: [keys.availability] })
  const code = new Map(analysts.map((a) => [a.id, a.employee_code]))
  return (
    <Card>
      <CardHeader><CardTitle>Availability exceptions</CardTitle>
        <CardDescription>Days an analyst cannot work at all, or cannot work specific shifts (hard rule, unlike preferences).</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <Table>
          <TableHeader><TableRow><TableHead>Analyst</TableHead><TableHead>Date</TableHead><TableHead>Kind</TableHead><TableHead>Note</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {data?.map((x) => (
              <TableRow key={x.id}>
                <TableCell>{code.get(x.analyst_id)}</TableCell><TableCell>{x.date}</TableCell>
                <TableCell>{x.kind === 'unavailable' ? 'Unavailable' : `No ${x.shift_codes.join('/')}`}</TableCell>
                <TableCell className="text-xs">{x.note}</TableCell>
                <TableCell className="text-right"><Button size="icon-xs" variant="ghost" aria-label="Delete exception" onClick={() => del.mutate(x.id)}><Trash2 /></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <form className="grid gap-2 sm:grid-cols-5" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined) }}>
          <NativeSelect aria-label="Exception analyst" value={f.analyst_id} onChange={(e) => setF({ ...f, analyst_id: e.target.value })}>
            <option value="">Analyst…</option>{analysts.map((a) => <option key={a.id} value={a.id}>{a.employee_code}</option>)}
          </NativeSelect>
          <Input type="date" aria-label="Exception date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
          <NativeSelect aria-label="Exception kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <option value="unavailable">Unavailable all day</option><option value="block_shifts">Block shifts…</option>
          </NativeSelect>
          <Input aria-label="Blocked shift codes" placeholder={f.kind === 'block_shifts' ? 'e.g. N' : 'Note'}
            value={f.kind === 'block_shifts' ? f.codes : f.note}
            onChange={(e) => setF(f.kind === 'block_shifts' ? { ...f, codes: e.target.value } : { ...f, note: e.target.value })} />
          <Button type="submit" variant="outline"><Plus /> Add</Button>
        </form>
        <ErrorAlert error={add.error} />
      </CardContent>
    </Card>
  )
}

function MappingsTab() {
  const { data } = useMappings()
  const [f, setF] = useState({ source_code: '', target_kind: 'shift', target_shift_code: '', description: '' })
  const add = useApiMutation(() => api.post('/shift-code-mappings', { ...f, target_shift_code: f.target_kind === 'shift' ? f.target_shift_code : null }),
    { invalidate: [keys.mappings], success: 'Mapping added' })
  const del = useApiMutation((id: number) => api.del(`/shift-code-mappings/${id}`), { invalidate: [keys.mappings] })
  return (
    <Card>
      <CardHeader><CardTitle>Historical shift-code mappings</CardTitle>
        <CardDescription>How codes in imported rosters (e.g. the previous SOC sheet) map to ShiftOrbit shifts and day types.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <Table>
          <TableHeader><TableRow><TableHead>Code in file</TableHead><TableHead>Means</TableHead><TableHead>Description</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {data?.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="font-mono">{m.source_code}</TableCell>
                <TableCell>{m.target_kind === 'shift' ? `shift ${m.target_shift_code}` : m.target_kind}</TableCell>
                <TableCell className="text-xs">{m.description}</TableCell>
                <TableCell className="text-right"><Button size="icon-xs" variant="ghost" aria-label={`Delete mapping ${m.source_code}`} onClick={() => del.mutate(m.id)}><Trash2 /></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <form className="grid gap-2 sm:grid-cols-5" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined) }}>
          <Input aria-label="Source code" placeholder="Code in file" value={f.source_code} onChange={(e) => setF({ ...f, source_code: e.target.value })} />
          <NativeSelect aria-label="Target kind" value={f.target_kind} onChange={(e) => setF({ ...f, target_kind: e.target.value })}>
            <option value="shift">Shift</option><option value="WO">Weekly off</option><option value="LEAVE">Leave</option><option value="H">Holiday</option>
          </NativeSelect>
          <Input aria-label="Target shift code" placeholder="Shift code" disabled={f.target_kind !== 'shift'} value={f.target_shift_code}
            onChange={(e) => setF({ ...f, target_shift_code: e.target.value })} />
          <Input aria-label="Mapping description" placeholder="Description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <Button type="submit" variant="outline"><Plus /> Add</Button>
        </form>
        <ErrorAlert error={add.error} />
      </CardContent>
    </Card>
  )
}

interface BackupInfo { name: string; size_bytes: number; created_at: string }

function DataTab() {
  const qc = useQueryClient()
  const backups = useQuery({ queryKey: ['backups'], queryFn: () => api.get<BackupInfo[]>('/admin/backups') })
  const [confirm, setConfirm] = useState('')
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const create = useApiMutation(() => api.post<BackupInfo>('/admin/backups'), { invalidate: [['backups']], success: (b) => `Backup ${b.name} created` })
  const restore = useApiMutation(() => {
    const fd = new FormData()
    fd.append('file', restoreFile as File)
    return api.post('/admin/restore', fd)
  }, { success: 'Database restored. Reloading…' })
  const wipe = useApiMutation(() => api.post('/admin/delete-all-data', { confirm }), { success: 'All local data deleted' })
  const demo = useApiMutation(() => api.post('/admin/demo-data'), { success: 'Synthetic demo data loaded' })
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Backups</CardTitle><CardDescription>Consistent copies of the SQLite database, stored locally in data/backups.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <Button onClick={() => create.mutate(undefined)} disabled={create.isPending}><DatabaseBackup /> Create backup now</Button>
          {backups.isLoading && <Loading />}
          <ul className="space-y-1 text-sm">
            {backups.data?.map((b) => (
              <li key={b.name} className="flex items-center justify-between gap-2">
                <span className="truncate">{b.name} · {(b.size_bytes / 1024).toFixed(0)} KB</span>
                <Button size="xs" variant="outline" onClick={() => downloadFile(`/admin/backups/${encodeURIComponent(b.name)}`, b.name).catch((e) => toast.error(errorMessage(e)))}>
                  <Download /> Download
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Restore</CardTitle><CardDescription>Replace the current database with a ShiftOrbit backup file. A safety backup of the current data is taken first.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <Input type="file" accept=".db,.sqlite,.sqlite3" aria-label="Backup file" onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)} />
          <Button variant="outline" disabled={!restoreFile || restore.isPending}
            onClick={() => window.confirm('Replace ALL current data with this backup?') && restore.mutate(undefined, { onSuccess: () => { void qc.invalidateQueries(); setTimeout(() => window.location.reload(), 800) } })}>
            <Upload /> Restore backup
          </Button>
          <ErrorAlert error={restore.error} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Synthetic demo data</CardTitle><CardDescription>Loads clearly labelled fictional projects and analysts (SYN-…) for trying the tool. Only works on an empty database.</CardDescription></CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => demo.mutate(undefined, { onSuccess: () => qc.invalidateQueries() })}>Load synthetic demo data</Button>
          <ErrorAlert error={demo.error} />
        </CardContent>
      </Card>
      <Card className="border-rose-500/40">
        <CardHeader><CardTitle className="text-rose-300">Delete all local data</CardTitle>
          <CardDescription>Permanently deletes every project, analyst, leave record, roster and backup from this computer. Type DELETE ALL DATA to confirm.</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          <Input aria-label="Confirmation phrase" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="DELETE ALL DATA" />
          <Button variant="destructive" disabled={confirm !== 'DELETE ALL DATA' || wipe.isPending}
            onClick={() => wipe.mutate(undefined, { onSuccess: () => { setConfirm(''); void qc.invalidateQueries() } })}>
            <Trash2 /> Delete everything
          </Button>
          <ErrorAlert error={wipe.error} />
        </CardContent>
      </Card>
    </div>
  )
}

export function SettingsPage() {
  return (
    <div>
      <PageHeader title="Settings & data" description="Scheduling rules, reference data and local data management." />
      <InfoAlert title="Local data">
        Everything is stored in a SQLite file on this computer. Nothing is uploaded and there is no telemetry.
      </InfoAlert>
      <Tabs defaultValue="policies">
        <TabsList className="flex-wrap">
          <TabsTrigger value="policies">Policies</TabsTrigger>
          <TabsTrigger value="reference">Skills & holidays</TabsTrigger>
          <TabsTrigger value="availability">Availability</TabsTrigger>
          <TabsTrigger value="mappings">Code mappings</TabsTrigger>
          <TabsTrigger value="data">Backup & data</TabsTrigger>
        </TabsList>
        <TabsContent value="policies"><PoliciesTab /></TabsContent>
        <TabsContent value="reference"><SimpleListTab /></TabsContent>
        <TabsContent value="availability"><AvailabilityTab /></TabsContent>
        <TabsContent value="mappings"><MappingsTab /></TabsContent>
        <TabsContent value="data"><DataTab /></TabsContent>
      </Tabs>
    </div>
  )
}
