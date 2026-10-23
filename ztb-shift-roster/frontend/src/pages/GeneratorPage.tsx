import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { EmptyState, ErrorAlert, Field, InfoAlert, Loading, NativeSelect, PageHeader, StatusBadge, ViolationList } from '@/components/common'
import { JobOutcome, JobProgress } from '@/components/JobProgress'
import { MonthPicker } from '@/components/MonthPicker'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { monthDates } from '@/lib/roster'
import { cn } from '@/lib/utils'
import { api, downloadFile, errorMessage } from '@/services/api'
import { useAnalysts, useLeaves, usePolicies, useProjects } from '@/services/queries'
import type { Feasibility, Job, Policy, Violation, Weights } from '@/types/api'

const STEPS = ['Month', 'Projects', 'Analysts', 'Leave', 'Rules', 'Feasibility', 'Generate', 'Validate', 'Review', 'Save / export']

type Overrides = Partial<Omit<Policy, 'id' | 'name' | 'is_default' | 'weights'>> & { weights?: Partial<Weights> }

const RULE_FIELDS: { key: keyof Overrides; label: string; hint?: string }[] = [
  { key: 'working_days_per_week', label: 'Working days per week' },
  { key: 'max_hours_per_week', label: 'Max hours per week' },
  { key: 'max_consecutive_work_days', label: 'Max consecutive working days' },
  { key: 'max_consecutive_nights', label: 'Max consecutive nights' },
  { key: 'min_rest_hours', label: 'Minimum rest between shifts (h)' },
]
const WEIGHT_FIELDS: { key: keyof Weights; label: string }[] = [
  { key: 'fair_nights', label: 'Fair night shifts' },
  { key: 'fair_weekends', label: 'Fair weekends' },
  { key: 'balanced_hours', label: 'Balanced hours' },
  { key: 'preferences', label: 'Shift preferences' },
  { key: 'shift_changes', label: 'Fewer shift changes' },
]

export function GeneratorPage() {
  const [step, setStep] = useState(0)
  // Default to next month, the usual month being planned.
  const [year, setYear] = useState(() => { const n = new Date(); return n.getMonth() === 11 ? n.getFullYear() + 1 : n.getFullYear() })
  const [month, setMonth] = useState(() => ((new Date().getMonth() + 1) % 12) + 1)
  const [projectIds, setProjectIds] = useState<number[]>([])
  const [analystIds, setAnalystIds] = useState<number[] | null>(null)
  const [simulateLeave, setSimulateLeave] = useState<number[]>([])
  const [policyId, setPolicyId] = useState<number | null>(null)
  const [overrides, setOverrides] = useState<Overrides>({})
  const [timeLimit, setTimeLimit] = useState('30')
  const [feasibility, setFeasibility] = useState<Feasibility | null>(null)
  const [feasError, setFeasError] = useState<unknown>(null)
  const [checking, setChecking] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [startError, setStartError] = useState<unknown>(null)

  const projects = useProjects()
  const analysts = useAnalysts()
  const policies = usePolicies()
  const dates = monthDates(year, month)
  const leaves = useLeaves({ start: dates[0], end: dates[dates.length - 1] })
  const policy = policies.data?.find((p) => (policyId == null ? p.is_default : p.id === policyId))

  const eligible = useMemo(() => (analysts.data ?? []).filter((a) => a.active &&
    a.eligibility.some((e) => projectIds.includes(e.project_id))), [analysts.data, projectIds])
  const selectedAnalysts = analystIds ?? eligible.map((a) => a.id)
  const monthLeaves = (leaves.data ?? []).filter((l) => selectedAnalysts.includes(l.analyst_id) &&
    (l.status === 'approved' || l.status === 'pending'))
  const code = new Map((analysts.data ?? []).map((a) => [a.id, a.employee_code]))

  const body = () => ({
    year, month, project_ids: projectIds, analyst_ids: analystIds, policy_id: policy?.id ?? null,
    policy_overrides: overrides, time_limit_seconds: Number(timeLimit) || 30,
    simulate_pending_leave_ids: simulateLeave,
  })

  const resetFrom = (s: number) => {
    if (s <= 5) setFeasibility(null)
    if (s <= 6) { setRunId(null); setJob(null) }
  }
  const go = (s: number) => setStep(Math.max(0, Math.min(STEPS.length - 1, s)))

  const runFeasibility = async () => {
    setChecking(true); setFeasError(null)
    try { setFeasibility(await api.post<Feasibility>('/rosters/feasibility', body())) } catch (e) { setFeasError(e) }
    setChecking(false)
  }
  const start = async () => {
    setStartError(null); setJob(null)
    try {
      const r = await api.post<{ run_id: string }>('/rosters/generate', body())
      setRunId(r.run_id)
    } catch (e) { setStartError(e) }
  }
  const canNext = [
    true, projectIds.length > 0, selectedAnalysts.length > 0, true, true, !!feasibility,
    !!job, !!job, !!job, false,
  ][step]
  const metrics = job?.result.validation?.metrics ?? {}
  const simulation = simulateLeave.length > 0

  return (
    <div>
      <PageHeader title="Roster generator" description="Build a month's roster with the CP-SAT optimiser in ten checked steps." />
      <ol className="mb-6 flex flex-wrap gap-1.5" aria-label="Wizard steps">
        {STEPS.map((label, i) => (
          <li key={label}>
            <button type="button" disabled={i > step} onClick={() => go(i)}
              className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs',
                i === step && 'border-primary bg-primary text-primary-foreground',
                i < step && 'border-emerald-500/50 text-emerald-300', i > step && 'opacity-50')}
              aria-current={i === step ? 'step' : undefined}>
              {i < step ? <Check className="size-3" /> : <span>{i + 1}</span>} {label}
            </button>
          </li>
        ))}
      </ol>

      <Card>
        <CardHeader><CardTitle>{step + 1}. {STEPS[step]}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {step === 0 && (
            <div className="space-y-3">
              <MonthPicker year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); resetFrom(0) }} />
              <p className="text-sm text-muted-foreground">
                The previous month's published roster (if any) is used for continuity: rest after the last night shift,
                consecutive days and the week spanning the month boundary.
              </p>
            </div>
          )}

          {step === 1 && (
            projects.isLoading ? <Loading /> : !projects.data?.length ? (
              <EmptyState title="No projects">Create a project first on <Link className="text-primary" to="/projects">Projects</Link>.</EmptyState>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {projects.data.filter((p) => p.active).map((p) => (
                  <label key={p.id} className="flex items-center gap-2 rounded-lg border p-3 text-sm">
                    <Checkbox checked={projectIds.includes(p.id)} onCheckedChange={(c) => {
                      setProjectIds(c ? [...projectIds, p.id] : projectIds.filter((x) => x !== p.id)); setAnalystIds(null); resetFrom(1)
                    }} aria-label={`Project ${p.code}`} />
                    <span><span className="font-medium">{p.code}</span> · {p.name}
                      <span className="block text-xs text-muted-foreground">
                        {p.shift_templates.filter((t) => t.active).map((t) => `${t.code} ${t.start_time}–${t.end_time}`).join(' · ')}
                      </span></span>
                  </label>
                ))}
              </div>
            )
          )}

          {step === 2 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Active analysts eligible for the selected projects. Untick anyone who should not be rostered.</p>
              {!eligible.length && <EmptyState title="No eligible analysts">Give analysts eligibility for these projects first.</EmptyState>}
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {eligible.map((a) => (
                  <label key={a.id} className="flex items-center gap-2 rounded-lg border p-2 text-sm">
                    <Checkbox checked={selectedAnalysts.includes(a.id)} aria-label={`Analyst ${a.employee_code}`}
                      onCheckedChange={(c) => { setAnalystIds(c ? [...selectedAnalysts, a.id] : selectedAnalysts.filter((x) => x !== a.id)); resetFrom(2) }} />
                    <span className="font-medium">{a.employee_code}</span><span className="truncate text-muted-foreground">{a.full_name}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{selectedAnalysts.length} selected</p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <InfoAlert title="How leave is used">
                Approved leave is always respected. Pending leave is ignored unless you tick it below; then the run becomes a
                simulation and nothing is saved. Add or import leave on the <Link className="text-primary" to="/leave">Leave</Link> and{' '}
                <Link className="text-primary" to="/import-export">Import</Link> pages.
              </InfoAlert>
              {leaves.isLoading && <Loading />}
              {!monthLeaves.length ? <p className="text-sm text-muted-foreground">No leave in this month for the selected analysts.</p> : (
                <Table>
                  <TableHeader><TableRow><TableHead>Analyst</TableHead><TableHead>Dates</TableHead><TableHead>Type</TableHead><TableHead>Status</TableHead><TableHead>Simulate</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {monthLeaves.map((l) => (
                      <TableRow key={l.id}>
                        <TableCell>{code.get(l.analyst_id)}</TableCell>
                        <TableCell>{l.start_date}{l.end_date !== l.start_date ? ` → ${l.end_date}` : ''}{l.partial_day ? ` ${l.start_time}–${l.end_time}` : ''}</TableCell>
                        <TableCell>{l.leave_type}</TableCell>
                        <TableCell><StatusBadge status={l.status} /></TableCell>
                        <TableCell>
                          {l.status === 'pending' && (
                            <Checkbox aria-label={`Simulate leave ${l.id}`} checked={simulateLeave.includes(l.id)}
                              onCheckedChange={(c) => { setSimulateLeave(c ? [...simulateLeave, l.id] : simulateLeave.filter((x) => x !== l.id)); resetFrom(3) }} />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}

          {step === 4 && policy && (
            <div className="space-y-4">
              <Field label="Scheduling policy" htmlFor="g-policy">
                <NativeSelect id="g-policy" value={policy.id} onChange={(e) => { setPolicyId(Number(e.target.value)); setOverrides({}); resetFrom(4) }}>
                  {policies.data?.map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_default ? ' (default)' : ''}</option>)}
                </NativeSelect>
              </Field>
              <p className="text-xs text-muted-foreground">Changes here apply to this run only. Hard rules are enforced exactly; they are never relaxed to force a result.</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {RULE_FIELDS.map((f) => (
                  <Field key={f.key} label={f.label} htmlFor={`g-${f.key}`}>
                    <Input id={`g-${f.key}`} inputMode="numeric" value={String(overrides[f.key] ?? policy[f.key as keyof Policy])}
                      onChange={(e) => { setOverrides({ ...overrides, [f.key]: e.target.value === '' ? undefined : Number(e.target.value) }); resetFrom(4) }} />
                  </Field>
                ))}
                <Field label="Weekly rule" htmlFor="g-mode">
                  <NativeSelect id="g-mode" value={overrides.weekly_mode ?? policy.weekly_mode}
                    onChange={(e) => { setOverrides({ ...overrides, weekly_mode: e.target.value as 'exact' | 'max' }); resetFrom(4) }}>
                    <option value="exact">Exactly N days (2 weekly offs)</option>
                    <option value="max">At most N days</option>
                  </NativeSelect>
                </Field>
                <Field label="Solver time limit (seconds)" htmlFor="g-limit" hint="1–600">
                  <Input id="g-limit" inputMode="numeric" value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)} />
                </Field>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium">Soft objective weights (0 = ignore)</p>
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {WEIGHT_FIELDS.map((f) => (
                    <Field key={f.key} label={f.label} htmlFor={`w-${f.key}`}>
                      <Input id={`w-${f.key}`} inputMode="numeric" value={String(overrides.weights?.[f.key] ?? policy.weights[f.key])}
                        onChange={(e) => setOverrides({ ...overrides, weights: { ...policy.weights, ...overrides.weights, [f.key]: Number(e.target.value) || 0 } })} />
                    </Field>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-3">
              <Button onClick={runFeasibility} disabled={checking}>{checking ? 'Checking…' : 'Run feasibility check'}</Button>
              <ErrorAlert error={feasError} />
              {feasibility && (
                <div className="space-y-2 text-sm" data-testid="feasibility">
                  <p className={feasibility.ok ? 'text-emerald-400' : 'text-rose-300'}>
                    {feasibility.ok ? 'No blockers found.' : `${feasibility.issues.length} definite blocker(s) found.`}
                  </p>
                  <p className="text-xs text-muted-foreground">{feasibility.disclaimer}</p>
                  <p className="text-xs">
                    {feasibility.summary.analysts} analysts · {feasibility.summary.days} days ·{' '}
                    {feasibility.summary.required_shift_positions} required positions · {feasibility.summary.candidate_slots} possible assignments
                  </p>
                  <ul className="list-disc space-y-0.5 pl-5">{feasibility.issues.slice(0, 40).map((i, n) => <li key={n} className="text-rose-300">{i.message}</li>)}</ul>
                  <ul className="list-disc space-y-0.5 pl-5">{feasibility.warnings.map((i, n) => <li key={n} className="text-muted-foreground">{i.message}</li>)}</ul>
                </div>
              )}
            </div>
          )}

          {step === 6 && (
            <div className="space-y-3">
              {simulation && <InfoAlert title="Simulation">Pending leave is included, so this run will not be saved as a roster.</InfoAlert>}
              {!runId && <Button onClick={start}><Play /> Generate roster</Button>}
              <ErrorAlert error={startError} />
              {runId && <JobProgress runId={runId} onDone={(j) => { setJob(j); if (j.roster_id) toast.success('Roster saved as draft') }} />}
              {job && <Button variant="outline" onClick={() => { setRunId(null); setJob(null) }}>Run again</Button>}
            </div>
          )}

          {step === 7 && job && (
            job.result.validation ? (
              <div className="space-y-2" data-testid="wizard-validation">
                <p className={job.result.validation.is_valid ? 'text-emerald-400' : 'text-rose-300'}>
                  Independent validator: {job.result.validation.is_valid ? 'every hard rule holds' : 'violations found'}
                  {' '}· coverage {job.result.validation.coverage_percent}%
                </p>
                <ViolationList violations={job.result.validation.violations as Violation[]} />
              </div>
            ) : <JobOutcome job={job} />
          )}

          {step === 8 && job && (
            Object.keys(metrics).length ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow><TableHead>Analyst</TableHead><TableHead className="text-right">Shifts</TableHead>
                    <TableHead className="text-right">Hours</TableHead><TableHead className="text-right">Nights</TableHead>
                    <TableHead className="text-right">Weekend</TableHead><TableHead className="text-right">Leave</TableHead><TableHead>By shift</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {Object.entries(metrics).map(([aid, m]) => (
                      <TableRow key={aid}>
                        <TableCell>{code.get(Number(aid))}</TableCell>
                        <TableCell className="text-right">{m.shifts}</TableCell><TableCell className="text-right">{m.hours}</TableCell>
                        <TableCell className="text-right">{m.nights}</TableCell><TableCell className="text-right">{m.weekend_shifts}</TableCell>
                        <TableCell className="text-right">{m.leave_days}</TableCell>
                        <TableCell className="text-xs">{Object.entries(m.by_code).map(([c, n]) => `${c}:${n}`).join(' ')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {job.result.objective_breakdown && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Objective terms (lower is better, 0 = perfectly even): {Object.entries(job.result.objective_breakdown).map(([k, n]) => `${k} ${n}`).join(' · ')}
                  </p>
                )}
              </div>
            ) : <JobOutcome job={job} />
          )}

          {step === 9 && job && (
            <div className="space-y-3">
              {job.roster_id ? (
                <>
                  <p className="text-sm">The roster was saved as a <strong>draft</strong>. Review and edit it, then publish.</p>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild><Link to={`/rosters/${job.roster_id}`}><ExternalLink /> Open roster editor</Link></Button>
                    <Button variant="outline" onClick={() => downloadFile(`/rosters/${job.roster_id}/export.xlsx`, 'roster.xlsx')
                      .catch((e) => toast.error(errorMessage(e)))}><Download /> Export XLSX</Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {simulation ? 'This was a simulation; nothing was saved.' : 'No roster was produced by this run.'} Go back to adjust and run again.
                </p>
              )}
            </div>
          )}

          <div className="flex justify-between border-t pt-4">
            <Button variant="outline" onClick={() => go(step - 1)} disabled={step === 0}><ChevronLeft /> Back</Button>
            {step < STEPS.length - 1 && (
              <Button onClick={() => go(step + 1)} disabled={!canNext}>Next <ChevronRight /></Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
