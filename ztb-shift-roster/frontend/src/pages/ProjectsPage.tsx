import { zodResolver } from '@hookform/resolvers/zod'
import { Moon, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { EmptyState, ErrorAlert, Field, Loading, NativeSelect, PageHeader, ShiftChip } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import {
  projectSchema,
  shiftMinutes,
  staffingSchema,
  templateSchema,
  type ProjectForm,
  type StaffingForm,
  type TemplateForm,
} from '@/lib/forms'
import { WEEKDAYS } from '@/lib/roster'
import { useApiMutation } from '@/lib/useApiMutation'
import { api } from '@/services/api'
import { keys, useProjects, useSkills } from '@/services/queries'
import type { Project, ShiftTemplate, Skill, Staffing } from '@/types/api'

function SkillPicker({ skills, value, onChange }: { skills: Skill[]; value: number[]; onChange: (v: number[]) => void }) {
  if (!skills.length) return <p className="text-xs text-muted-foreground">No skills defined (Settings → Skills).</p>
  return (
    <div className="flex flex-wrap gap-3">
      {skills.map((s) => (
        <label key={s.id} className="flex items-center gap-1.5 text-sm">
          <Checkbox checked={value.includes(s.id)}
            onCheckedChange={(c) => onChange(c ? [...value, s.id] : value.filter((x) => x !== s.id))} />
          {s.name}
        </label>
      ))}
    </div>
  )
}

function ProjectDialog({ project, open, onClose }: { project: Project | null; open: boolean; onClose: () => void }) {
  const { data: skills = [] } = useSkills()
  const [skillIds, setSkillIds] = useState<number[]>(project?.required_skill_ids ?? [])
  const [defaults, setDefaults] = useState(true)
  const form = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
    values: {
      code: project?.code ?? '', name: project?.name ?? '', description: project?.description ?? '',
      timezone: project?.timezone ?? 'Asia/Kolkata', active: project?.active ?? true,
    },
  })
  const save = useApiMutation(
    (v: ProjectForm) => project
      ? api.put(`/projects/${project.id}`, { ...v, required_skill_ids: skillIds })
      : api.post('/projects', { ...v, required_skill_ids: skillIds, create_default_shifts: defaults }),
    { invalidate: [keys.projects], success: project ? 'Project updated' : 'Project created' },
  )
  const errors = form.formState.errors
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{project ? `Edit ${project.code}` : 'New project'}</DialogTitle></DialogHeader>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: onClose }))}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Code" htmlFor="p-code" error={errors.code?.message}>
              <Input id="p-code" {...form.register('code')} />
            </Field>
            <Field label="Timezone" htmlFor="p-tz" error={errors.timezone?.message}>
              <Input id="p-tz" {...form.register('timezone')} />
            </Field>
          </div>
          <Field label="Name" htmlFor="p-name" error={errors.name?.message}>
            <Input id="p-name" {...form.register('name')} />
          </Field>
          <Field label="Description" htmlFor="p-desc" error={errors.description?.message}>
            <Textarea id="p-desc" rows={2} {...form.register('description')} />
          </Field>
          <div className="grid gap-1.5">
            <Label>Required skills</Label>
            <SkillPicker skills={skills} value={skillIds} onChange={setSkillIds} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={form.watch('active')} onCheckedChange={(c) => form.setValue('active', !!c)} /> Active
          </label>
          {!project && (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={defaults} onCheckedChange={(c) => setDefaults(!!c)} />
              Create default shifts (M 06–15, A 14–23, N 22–07) with minimum 1 analyst each
            </label>
          )}
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

function TemplateDialog({ projectId, template, open, onClose }: {
  projectId: number
  template: ShiftTemplate | null
  open: boolean
  onClose: () => void
}) {
  const { data: skills = [] } = useSkills()
  const [skillIds, setSkillIds] = useState<number[]>(template?.required_skill_ids ?? [])
  const form = useForm<TemplateForm>({
    resolver: zodResolver(templateSchema),
    values: {
      code: template?.code ?? '', name: template?.name ?? '', start_time: template?.start_time ?? '09:00',
      end_time: template?.end_time ?? '18:00', is_night: template?.is_night ?? false,
      color: template?.color ?? '#22c55e', active: template?.active ?? true,
    },
  })
  const save = useApiMutation(
    (v: TemplateForm) => {
      const body = { ...v, code: v.code.toUpperCase(), required_skill_ids: skillIds }
      return template ? api.put(`/shift-templates/${template.id}`, body)
        : api.post(`/projects/${projectId}/shift-templates`, body)
    },
    { invalidate: [keys.projects], success: 'Shift saved' },
  )
  const errors = form.formState.errors
  const start = form.watch('start_time')
  const end = form.watch('end_time')
  const ok = /^\d\d:\d\d$/.test(start) && /^\d\d:\d\d$/.test(end)
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{template ? `Edit shift ${template.code}` : 'New shift template'}</DialogTitle></DialogHeader>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: onClose }))}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Code" htmlFor="t-code" error={errors.code?.message} hint="e.g. M, A, N, D, AN">
              <Input id="t-code" {...form.register('code')} />
            </Field>
            <Field label="Name" htmlFor="t-name" error={errors.name?.message}>
              <Input id="t-name" {...form.register('name')} />
            </Field>
            <Field label="Start (project local time)" htmlFor="t-start" error={errors.start_time?.message}>
              <Input id="t-start" type="time" {...form.register('start_time')} />
            </Field>
            <Field label="End" htmlFor="t-end" error={errors.end_time?.message}
              hint={ok ? `${(shiftMinutes(start, end) / 60).toFixed(1)} h${end <= start ? ', ends next day' : ''}` : ''}>
              <Input id="t-end" type="time" {...form.register('end_time')} />
            </Field>
            <Field label="Colour" htmlFor="t-color" error={errors.color?.message}>
              <Input id="t-color" type="color" className="h-8 p-1" {...form.register('color')} />
            </Field>
          </div>
          <div className="grid gap-1.5">
            <Label>Required skills for this shift</Label>
            <SkillPicker skills={skills} value={skillIds} onChange={setSkillIds} />
          </div>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={form.watch('is_night')} onCheckedChange={(c) => form.setValue('is_night', !!c)} />
              Night shift (counts toward night fairness and night limits)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={form.watch('active')} onCheckedChange={(c) => form.setValue('active', !!c)} /> Active
            </label>
          </div>
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

function StaffingDialog({ project, open, onClose }: { project: Project; open: boolean; onClose: () => void }) {
  const form = useForm<StaffingForm>({
    resolver: zodResolver(staffingSchema),
    defaultValues: { shift_template_id: '', day: '', specific_date: '', min_staff: '1', max_staff: '' },
  })
  const save = useApiMutation(
    (v: StaffingForm) => api.post(`/projects/${project.id}/staffing`, {
      shift_template_id: Number(v.shift_template_id),
      weekday: v.day !== '' && v.day !== 'date' ? Number(v.day) : null,
      specific_date: v.day === 'date' ? v.specific_date : null,
      min_staff: Number(v.min_staff),
      max_staff: v.max_staff === '' ? null : Number(v.max_staff),
    }),
    { invalidate: [keys.projects], success: 'Requirement added' },
  )
  const errors = form.formState.errors
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Staffing requirement · {project.code}</DialogTitle></DialogHeader>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => save.mutate(v, { onSuccess: () => { form.reset(); onClose() } }))}>
          <Field label="Shift" htmlFor="s-tpl" error={errors.shift_template_id?.message}>
            <NativeSelect id="s-tpl" {...form.register('shift_template_id')}>
              <option value="">Choose…</option>
              {project.shift_templates.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Applies to" htmlFor="s-day" hint="A specific date overrides a weekday, which overrides 'every day'.">
            <NativeSelect id="s-day" {...form.register('day')}>
              <option value="">Every day</option>
              {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
              <option value="date">Specific date…</option>
            </NativeSelect>
          </Field>
          {form.watch('day') === 'date' && (
            <Field label="Date" htmlFor="s-date" error={errors.specific_date?.message}>
              <Input id="s-date" type="date" {...form.register('specific_date')} />
            </Field>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Minimum analysts" htmlFor="s-min" error={errors.min_staff?.message}>
              <Input id="s-min" inputMode="numeric" {...form.register('min_staff')} />
            </Field>
            <Field label="Maximum (optional)" htmlFor="s-max" error={errors.max_staff?.message}>
              <Input id="s-max" inputMode="numeric" {...form.register('max_staff')} />
            </Field>
          </div>
          <ErrorAlert error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>Add</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function StaffingRowEditor({ req, onSaved }: { req: Staffing; onSaved: () => void }) {
  const [min, setMin] = useState(String(req.min_staff))
  const save = useApiMutation(
    () => api.put(`/staffing/${req.id}`, { shift_template_id: req.shift_template_id, weekday: req.weekday,
      specific_date: req.specific_date, min_staff: Number(min), max_staff: req.max_staff }),
    { invalidate: [keys.projects], success: 'Minimum updated' },
  )
  return (
    <Input aria-label="Minimum staff" className="h-7 w-16" value={min} inputMode="numeric"
      onChange={(e) => setMin(e.target.value)}
      onBlur={() => { if (min !== String(req.min_staff) && /^\d+$/.test(min)) save.mutate(undefined, { onSuccess: onSaved }) }} />
  )
}

function ProjectCard({ project }: { project: Project }) {
  const [editProject, setEditProject] = useState(false)
  const [tpl, setTpl] = useState<ShiftTemplate | null | 'new'>(null)
  const [staffing, setStaffing] = useState(false)
  const del = useApiMutation(() => api.del(`/projects/${project.id}`), { invalidate: [keys.projects], success: 'Project deleted' })
  const delTpl = useApiMutation((id: number) => api.del(`/shift-templates/${id}`), { invalidate: [keys.projects], success: 'Shift deleted' })
  const delReq = useApiMutation((id: number) => api.del(`/staffing/${id}`), { invalidate: [keys.projects] })
  const tplById = new Map(project.shift_templates.map((t) => [t.id, t]))
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {project.code} <span className="font-normal text-muted-foreground">· {project.name}</span>
          {!project.active && <Badge variant="secondary">inactive</Badge>}
        </CardTitle>
        <CardDescription>{project.timezone}{project.description ? ` · ${project.description}` : ''}</CardDescription>
        <CardAction className="flex gap-1">
          <Button size="icon-sm" variant="ghost" aria-label={`Edit project ${project.code}`} onClick={() => setEditProject(true)}><Pencil /></Button>
          <Button size="icon-sm" variant="ghost" aria-label={`Delete project ${project.code}`}
            onClick={() => window.confirm(`Delete project ${project.code}? Drafts using it are deleted too.`) && del.mutate(undefined)}>
            <Trash2 />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-6 xl:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium">Shift templates</h3>
            <Button size="sm" variant="outline" onClick={() => setTpl('new')}><Plus /> Shift</Button>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead>Shift</TableHead><TableHead>Time</TableHead><TableHead>Hours</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {project.shift_templates.map((t) => (
                <TableRow key={t.id} className={t.active ? '' : 'opacity-50'}>
                  <TableCell className="flex items-center gap-2"><ShiftChip code={t.code} color={t.color} /> {t.name}
                    {t.is_night && <Moon className="size-3.5 text-indigo-300" aria-label="night" />}</TableCell>
                  <TableCell className="tabular-nums">{t.start_time}–{t.end_time}{t.overnight ? ' (+1)' : ''}</TableCell>
                  <TableCell className="tabular-nums">{((t.duration_minutes ?? 0) / 60).toFixed(1)}</TableCell>
                  <TableCell className="text-right">
                    <Button size="icon-xs" variant="ghost" aria-label={`Edit shift ${t.code}`} onClick={() => setTpl(t)}><Pencil /></Button>
                    <Button size="icon-xs" variant="ghost" aria-label={`Delete shift ${t.code}`}
                      onClick={() => window.confirm(`Delete shift ${t.code}?`) && delTpl.mutate(t.id)}><Trash2 /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium">Staffing requirements</h3>
            <Button size="sm" variant="outline" onClick={() => setStaffing(true)}><Plus /> Requirement</Button>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead>Shift</TableHead><TableHead>Applies to</TableHead><TableHead>Min</TableHead><TableHead>Max</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {project.staffing.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{tplById.get(r.shift_template_id)?.code ?? '?'}</TableCell>
                  <TableCell>{r.specific_date ?? (r.weekday != null ? WEEKDAYS[r.weekday] : 'Every day')}</TableCell>
                  <TableCell><StaffingRowEditor req={r} onSaved={() => undefined} /></TableCell>
                  <TableCell>{r.max_staff ?? '—'}</TableCell>
                  <TableCell className="text-right">
                    <Button size="icon-xs" variant="ghost" aria-label="Delete requirement" onClick={() => delReq.mutate(r.id)}><Trash2 /></Button>
                  </TableCell>
                </TableRow>
              ))}
              {!project.staffing.length && (
                <TableRow><TableCell colSpan={5} className="text-muted-foreground">No requirements: shifts will have minimum 0.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
      {editProject && <ProjectDialog project={project} open onClose={() => setEditProject(false)} />}
      {tpl && <TemplateDialog projectId={project.id} template={tpl === 'new' ? null : tpl} open onClose={() => setTpl(null)} />}
      {staffing && <StaffingDialog project={project} open onClose={() => setStaffing(false)} />}
    </Card>
  )
}

export function ProjectsPage() {
  const { data, isLoading, error } = useProjects()
  const [creating, setCreating] = useState(false)
  return (
    <div>
      <PageHeader title="Projects & shifts" description="Projects, their shift timings and minimum staffing per shift."
        actions={<Button onClick={() => setCreating(true)}><Plus /> New project</Button>} />
      <ErrorAlert error={error} />
      {isLoading && <Loading />}
      {data && !data.length && <EmptyState title="No projects yet">Create the first SOC project to get started.</EmptyState>}
      <div className="space-y-4">{data?.map((p) => <ProjectCard key={p.id} project={p} />)}</div>
      {creating && <ProjectDialog project={null} open onClose={() => setCreating(false)} />}
    </div>
  )
}
