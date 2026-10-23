import { zodResolver } from '@hookform/resolvers/zod'
import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'

import { EmptyState, ErrorAlert, Field, Loading, NativeSelect, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { analystSchema, splitCodes, type AnalystForm } from '@/lib/forms'
import { WEEKDAYS } from '@/lib/roster'
import { useApiMutation } from '@/lib/useApiMutation'
import { api } from '@/services/api'
import { keys, useAnalysts, useProjects, useSkills } from '@/services/queries'
import type { Analyst } from '@/types/api'

function toForm(a: Analyst | null): AnalystForm {
  return {
    employee_code: a?.employee_code ?? '',
    full_name: a?.full_name ?? '',
    email: a?.email ?? '',
    active: a?.active ?? true,
    max_hours_per_week: a?.max_hours_per_week != null ? String(a.max_hours_per_week) : '',
    notes: a?.notes ?? '',
    preferred_shifts: (a?.preferences.preferred_shifts ?? []).join(', '),
    avoid_shifts: (a?.preferences.avoid_shifts ?? []).join(', '),
    preferred_off_days: a?.preferences.preferred_off_days ?? [],
    skill_ids: a?.skill_ids ?? [],
    eligibility: (a?.eligibility ?? []).map((e) => ({
      project_id: e.project_id, allowed_shift_codes: e.allowed_shift_codes.join(', '), is_primary: e.is_primary,
    })),
  }
}

function AnalystDialog({ analyst, onClose }: { analyst: Analyst | null; onClose: () => void }) {
  const { data: projects = [] } = useProjects()
  const { data: skills = [] } = useSkills()
  const form = useForm<AnalystForm>({ resolver: zodResolver(analystSchema), defaultValues: toForm(analyst) })
  const elig = useFieldArray({ control: form.control, name: 'eligibility' })
  const save = useApiMutation(
    (v: AnalystForm) => {
      const body = {
        employee_code: v.employee_code, full_name: v.full_name, email: v.email || null, active: v.active,
        max_hours_per_week: v.max_hours_per_week ? Number(v.max_hours_per_week) : null, notes: v.notes,
        skill_ids: v.skill_ids,
        preferences: { preferred_shifts: splitCodes(v.preferred_shifts), avoid_shifts: splitCodes(v.avoid_shifts),
          preferred_off_days: v.preferred_off_days },
        eligibility: v.eligibility.map((e) => ({ project_id: e.project_id,
          allowed_shift_codes: splitCodes(e.allowed_shift_codes), is_primary: e.is_primary })),
      }
      return analyst ? api.put(`/analysts/${analyst.id}`, body) : api.post('/analysts', body)
    },
    { invalidate: [keys.analysts], success: analyst ? 'Analyst updated' : 'Analyst added' },
  )
  const errors = form.formState.errors
  const offDays = form.watch('preferred_off_days')
  const skillIds = form.watch('skill_ids')
  const used = new Set(form.watch('eligibility').map((e) => e.project_id))
  const free = projects.filter((p) => !used.has(p.id))
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle>{analyst ? `Edit ${analyst.employee_code}` : 'New analyst'}</DialogTitle></DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: onClose }))}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Employee code" htmlFor="a-code" error={errors.employee_code?.message}>
              <Input id="a-code" {...form.register('employee_code')} />
            </Field>
            <Field label="Full name" htmlFor="a-name" error={errors.full_name?.message}>
              <Input id="a-name" {...form.register('full_name')} />
            </Field>
            <Field label="Email (optional, stays local)" htmlFor="a-email" error={errors.email?.message}>
              <Input id="a-email" {...form.register('email')} />
            </Field>
            <Field label="Max hours / week (blank = policy)" htmlFor="a-hours" error={errors.max_hours_per_week?.message}>
              <Input id="a-hours" inputMode="numeric" {...form.register('max_hours_per_week')} />
            </Field>
          </div>

          <div className="grid gap-2">
            <Label>Project eligibility</Label>
            {elig.fields.map((f, i) => {
              const p = projects.find((x) => x.id === f.project_id)
              return (
                <div key={f.id} className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2">
                  <span className="text-sm font-medium">{p ? `${p.code} · ${p.name}` : `#${f.project_id}`}</span>
                  <Input aria-label="Allowed shifts" placeholder="Allowed shifts (blank = all), e.g. M, A"
                    {...form.register(`eligibility.${i}.allowed_shift_codes`)} />
                  <label className="flex items-center gap-1 text-xs">
                    <Checkbox checked={form.watch(`eligibility.${i}.is_primary`)}
                      onCheckedChange={(c) => form.watch('eligibility').forEach((_, j) =>
                        form.setValue(`eligibility.${j}.is_primary`, j === i ? !!c : false))} />
                    Primary
                  </label>
                  <Button type="button" size="icon-sm" variant="ghost" aria-label="Remove project" onClick={() => elig.remove(i)}>
                    <Trash2 />
                  </Button>
                </div>
              )
            })}
            {free.length > 0 && (
              <NativeSelect aria-label="Add project" value="" onChange={(e) => e.target.value &&
                elig.append({ project_id: Number(e.target.value), allowed_shift_codes: '', is_primary: elig.fields.length === 0 })}>
                <option value="">+ Add eligible project…</option>
                {free.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </NativeSelect>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label>Skills</Label>
            {skills.length ? (
              <div className="flex flex-wrap gap-3">
                {skills.map((s) => (
                  <label key={s.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox checked={skillIds.includes(s.id)} onCheckedChange={(c) => form.setValue('skill_ids',
                      c ? [...skillIds, s.id] : skillIds.filter((x) => x !== s.id))} />
                    {s.name}
                  </label>
                ))}
              </div>
            ) : <p className="text-xs text-muted-foreground">No skills defined (Settings → Skills).</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Preferred shifts" htmlFor="a-pref" hint="Soft preference, e.g. M, A">
              <Input id="a-pref" {...form.register('preferred_shifts')} />
            </Field>
            <Field label="Shifts to avoid" htmlFor="a-avoid" hint="Soft preference, e.g. N">
              <Input id="a-avoid" {...form.register('avoid_shifts')} />
            </Field>
          </div>
          <div className="grid gap-1.5">
            <Label>Preferred days off (soft)</Label>
            <div className="flex flex-wrap gap-3">
              {WEEKDAYS.map((d, i) => (
                <label key={d} className="flex items-center gap-1 text-sm">
                  <Checkbox checked={offDays.includes(i)} onCheckedChange={(c) => form.setValue('preferred_off_days',
                    c ? [...offDays, i] : offDays.filter((x) => x !== i))} />{d}
                </label>
              ))}
            </div>
          </div>
          <Field label="Notes" htmlFor="a-notes"><Textarea id="a-notes" rows={2} {...form.register('notes')} /></Field>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={form.watch('active')} onCheckedChange={(c) => form.setValue('active', !!c)} /> Active
          </label>
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

export function AnalystsPage() {
  const { data, isLoading, error } = useAnalysts()
  const { data: projects = [] } = useProjects()
  const { data: skills = [] } = useSkills()
  const [editing, setEditing] = useState<Analyst | null | 'new'>(null)
  const [search, setSearch] = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const del = useApiMutation((id: number) => api.del(`/analysts/${id}`), { invalidate: [keys.analysts], success: 'Analyst deleted' })
  const projectCode = new Map(projects.map((p) => [p.id, p.code]))
  const skillName = new Map(skills.map((s) => [s.id, s.name]))
  const rows = useMemo(() => (data ?? []).filter((a) =>
    (!search || `${a.employee_code} ${a.full_name}`.toLowerCase().includes(search.toLowerCase())) &&
    (!projectFilter || a.eligibility.some((e) => e.project_id === Number(projectFilter)))), [data, search, projectFilter])
  return (
    <div>
      <PageHeader title="Analysts" description="Who can work which projects and shifts, with skills and preferences."
        actions={<Button onClick={() => setEditing('new')}><Plus /> New analyst</Button>} />
      <ErrorAlert error={error} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative sm:w-72">
          <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Search analysts" className="pl-8" placeholder="Search code or name" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
        <NativeSelect aria-label="Filter by project" className="sm:w-56" value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
        </NativeSelect>
      </div>
      {isLoading && <Loading />}
      {data && !data.length && <EmptyState title="No analysts yet">Add analysts or import them from Excel/CSV.</EmptyState>}
      {rows.length > 0 && (
        <Card className="py-0">
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Projects</TableHead>
                  <TableHead className="hidden md:table-cell">Skills</TableHead>
                  <TableHead className="hidden md:table-cell">Preferences</TableHead><TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((a) => (
                  <TableRow key={a.id} className={a.active ? '' : 'opacity-50'}>
                    <TableCell className="font-medium">{a.employee_code}</TableCell>
                    <TableCell>{a.full_name}{!a.active && <Badge variant="secondary" className="ml-2">inactive</Badge>}</TableCell>
                    <TableCell className="space-x-1">
                      {a.eligibility.map((e) => (
                        <Badge key={e.project_id} variant={e.is_primary ? 'default' : 'secondary'}>
                          {projectCode.get(e.project_id)}{e.allowed_shift_codes.length ? ` (${e.allowed_shift_codes.join('/')})` : ''}
                        </Badge>
                      ))}
                    </TableCell>
                    <TableCell className="hidden text-xs md:table-cell">{a.skill_ids.map((s) => skillName.get(s)).join(', ') || '—'}</TableCell>
                    <TableCell className="hidden text-xs md:table-cell">
                      {[a.preferences.preferred_shifts?.length ? `prefers ${a.preferences.preferred_shifts.join('/')}` : '',
                        a.preferences.avoid_shifts?.length ? `avoids ${a.preferences.avoid_shifts.join('/')}` : '',
                        a.preferences.preferred_off_days?.length ? `off ${a.preferences.preferred_off_days.map((d) => WEEKDAYS[d]).join('/')}` : '',
                      ].filter(Boolean).join(' · ') || '—'}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${a.employee_code}`} onClick={() => setEditing(a)}><Pencil /></Button>
                      <Button size="icon-sm" variant="ghost" aria-label={`Delete ${a.employee_code}`}
                        onClick={() => window.confirm(`Delete ${a.employee_code}?`) && del.mutate(a.id)}><Trash2 /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      {editing && <AnalystDialog analyst={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
