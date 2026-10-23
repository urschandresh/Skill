import { Loader2, Square } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { ErrorAlert, StatusBadge, ViolationList } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useApiMutation } from '@/lib/useApiMutation'
import { api } from '@/services/api'
import { useJob } from '@/services/queries'
import type { Job, Violation } from '@/types/api'

const PHASES: Record<string, string> = {
  preparing: 'Preparing data',
  building_model: 'Building the CP-SAT model',
  solving: 'Solving',
  diagnosing: 'Finding conflicting rules',
  validating: 'Independent validation',
}

function fmt(n: number | undefined | null) {
  return n == null ? '—' : Math.round(n).toLocaleString()
}

/** Live job status. Shows only what the solver actually reports: no invented percentages. */
export function JobProgress({ runId, onDone }: { runId: string; onDone?: (job: Job) => void }) {
  const { data: job, error } = useJob(runId)
  const cancel = useApiMutation(() => api.post(`/jobs/${runId}/cancel`), { success: 'Cancellation requested' })
  const notified = useRef(false)
  const active = job && (job.state === 'queued' || job.state === 'running')

  useEffect(() => {
    if (job && !active && !notified.current) {
      notified.current = true
      onDone?.(job)
    }
  }, [job, active, onDone])

  if (error) return <ErrorAlert error={error} />
  if (!job) return <p className="text-sm text-muted-foreground">Starting…</p>
  const p = job.progress
  const limit = p.time_limit_seconds ?? job.time_limit_seconds ?? undefined
  const elapsed = p.elapsed_seconds ?? 0
  return (
    <div className="space-y-3 rounded-lg border p-4" data-testid="job-progress">
      <div className="flex flex-wrap items-center gap-2">
        {active && <Loader2 className="size-4 animate-spin text-primary" />}
        <span className="text-sm font-medium">
          {active ? PHASES[p.phase ?? ''] ?? 'Queued' : 'Run finished'}
        </span>
        <StatusBadge status={job.state} />
        <StatusBadge status={job.solver_status} />
        {active && (
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => cancel.mutate(undefined)} disabled={cancel.isPending}>
            <Square /> Cancel
          </Button>
        )}
      </div>
      {active && limit ? (
        <div>
          <Progress value={Math.min(100, (100 * elapsed) / limit)} aria-label="Time used of the solver limit" />
          <p className="mt-1 text-xs text-muted-foreground">
            {elapsed.toFixed(1)} s of the {limit} s time limit used (time, not completion: the solver may finish earlier)
          </p>
        </div>
      ) : null}
      {active && (
        <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div><dt className="text-muted-foreground">Solutions found</dt><dd className="tabular-nums">{p.solutions_found ?? 0}</dd></div>
          <div><dt className="text-muted-foreground">Best objective</dt><dd className="tabular-nums">{fmt(p.objective)}</dd></div>
          <div><dt className="text-muted-foreground">Proven bound</dt><dd className="tabular-nums">{fmt(p.best_bound)}</dd></div>
          <div><dt className="text-muted-foreground">Variables</dt><dd className="tabular-nums">{fmt(p.decision_variables)}</dd></div>
        </dl>
      )}
      {!active && <JobOutcome job={job} />}
    </div>
  )
}

export function JobOutcome({ job }: { job: Job }) {
  const r = job.result
  const diagnostics = (r.diagnostics ?? []) as Record<string, unknown>[]
  return (
    <div className="space-y-2 text-sm">
      <p>{job.message || r.message}</p>
      {r.wall_time_seconds != null && (
        <p className="text-xs text-muted-foreground">
          {r.wall_time_seconds}s · {r.solutions_found ?? 0} solutions
          {r.objective != null && ` · objective ${fmt(r.objective)} (bound ${fmt(r.best_bound)})`}
          {r.stopped_by_user && ' · stopped by user'}
        </p>
      )}
      {r.changes && <p>Would change {r.changes.removed} existing and add {r.changes.added} assignments.</p>}
      {diagnostics.length > 0 && (
        <div>
          <p className="font-medium text-rose-300">
            {r.proven_by === 'preliminary_check' ? 'Found before solving:' : 'Conflicting rule groups:'}
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
            {diagnostics.slice(0, 30).map((d, i) => (
              <li key={i}>{String(d.message ?? `${d.type}: ${JSON.stringify(d)}`)}</li>
            ))}
          </ul>
        </div>
      )}
      {r.validation && (
        <div>
          <p className="font-medium">Independent validation: {r.validation.is_valid ? 'passed' : 'failed'}
            {' '}· coverage {r.validation.coverage_percent}%</p>
          <ViolationList violations={(r.validation.violations ?? []) as Violation[]} max={10} />
        </div>
      )}
      {r.notes?.length ? <ul className="list-disc pl-5 text-xs text-muted-foreground">{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
    </div>
  )
}
