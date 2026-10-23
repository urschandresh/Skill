import { AlertTriangle, CalendarCheck, FolderKanban, Palmtree, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ErrorAlert, Loading, PageHeader, StatCard, StatusBadge } from '@/components/common'
import { MonthPicker } from '@/components/MonthPicker'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDashboard } from '@/services/queries'

const SHIFT_COLORS: Record<string, string> = { M: '#38bdf8', A: '#f59e0b', N: '#6366f1', D: '#22c55e', AN: '#f43f5e' }

export function DashboardPage() {
  const [ym, setYm] = useState<[number, number]>(() => {
    const now = new Date()
    return [now.getFullYear(), now.getMonth() + 1]
  })
  const { data, isLoading, error } = useDashboard(ym[0], ym[1])

  const maxHours = Math.max(1, ...(data?.workload.map((w) => w.hours) ?? [1]))
  const byProject = new Map<string, { shift: string; count: number }[]>()
  for (const d of data?.shift_distribution ?? []) {
    byProject.set(d.project, [...(byProject.get(d.project) ?? []), { shift: d.shift, count: d.count }])
  }

  return (
    <div>
      <PageHeader
        title="Operations dashboard"
        description="Coverage, workload and roster status for the selected month."
        actions={<MonthPicker year={ym[0]} month={ym[1]} onChange={(y, m) => setYm([y, m])} />}
      />
      <ErrorAlert error={error} />
      {isLoading && <Loading />}
      {data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Projects" value={data.totals.projects} icon={<FolderKanban className="size-5" />} />
            <StatCard label="Active analysts" value={data.totals.active_analysts} icon={<Users className="size-5" />} />
            <StatCard label="Pending leaves" value={data.totals.pending_leaves}
              tone={data.totals.pending_leaves ? 'warn' : 'default'}
              hint={`${data.totals.approved_leaves_this_month} approved this month`} icon={<Palmtree className="size-5" />} />
            <StatCard label="Coverage" value={data.coverage_percent == null ? '—' : `${data.coverage_percent}%`}
              tone={data.coverage_percent == null ? 'default' : data.coverage_percent >= 100 ? 'good' : 'warn'}
              hint={data.rosters.length ? 'Shift-days meeting minimum staffing' : 'No roster for this month yet'}
              icon={<CalendarCheck className="size-5" />} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader>
                <CardTitle>Staffing alerts</CardTitle>
                <CardDescription>Shortfalls and rule conflicts in this month's current roster.</CardDescription>
              </CardHeader>
              <CardContent>
                {!data.rosters.length ? (
                  <p className="text-sm text-muted-foreground">
                    No roster yet. <Link className="text-primary underline" to="/generate">Generate one</Link>.
                  </p>
                ) : data.alerts.length === 0 ? (
                  <p className="text-sm text-emerald-400">No staffing shortages or conflicts.</p>
                ) : (
                  <ul className="max-h-72 space-y-2 overflow-auto text-sm" data-testid="alerts">
                    {data.alerts.map((a, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-400" />
                        <Link to={`/rosters/${a.roster_id}`} className="hover:underline">{a.message}</Link>
                      </li>
                    ))}
                    {data.alert_count > data.alerts.length && (
                      <li className="text-muted-foreground">…and {data.alert_count - data.alerts.length} more</li>
                    )}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Shift distribution</CardTitle>
                <CardDescription>Assignments per shift in the current roster.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {byProject.size === 0 && <p className="text-sm text-muted-foreground">No assignments.</p>}
                {[...byProject.entries()].map(([project, items]) => {
                  const total = items.reduce((s, x) => s + x.count, 0)
                  return (
                    <div key={project}>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">{project} · {total} shifts</p>
                      <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img"
                        aria-label={items.map((x) => `${x.shift} ${x.count}`).join(', ')}>
                        {items.map((x) => (
                          <div key={x.shift} style={{ width: `${(100 * x.count) / total}%`,
                            backgroundColor: SHIFT_COLORS[x.shift] ?? '#94a3b8' }} />
                        ))}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-3 text-xs">
                        {items.map((x) => (
                          <span key={x.shift} className="flex items-center gap-1">
                            <span className="size-2 rounded-full" style={{ backgroundColor: SHIFT_COLORS[x.shift] ?? '#94a3b8' }} />
                            {x.shift} {x.count}
                          </span>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader>
                <CardTitle>Monthly workload</CardTitle>
                <CardDescription>Hours, nights and weekend shifts per analyst.</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Analyst</TableHead>
                      <TableHead className="w-1/3">Hours</TableHead>
                      <TableHead className="text-right">Shifts</TableHead>
                      <TableHead className="text-right">Nights</TableHead>
                      <TableHead className="text-right">Weekend</TableHead>
                      <TableHead className="text-right">Leave days</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.workload.map((w) => (
                      <TableRow key={w.analyst_id}>
                        <TableCell>
                          <span className="font-medium">{w.employee_code}</span>
                          <span className="ml-2 text-xs text-muted-foreground">{w.full_name}</span>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="h-2 flex-1 rounded-full bg-muted">
                              <div className="h-2 rounded-full bg-primary" style={{ width: `${(100 * w.hours) / maxHours}%` }} />
                            </div>
                            <span className="w-12 text-right text-xs tabular-nums">{w.hours}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{w.shifts}</TableCell>
                        <TableCell className="text-right tabular-nums">{w.nights}</TableCell>
                        <TableCell className="text-right tabular-nums">{w.weekend_shifts}</TableCell>
                        <TableCell className="text-right tabular-nums">{w.leave_days}</TableCell>
                      </TableRow>
                    ))}
                    {!data.workload.length && (
                      <TableRow><TableCell colSpan={6} className="text-muted-foreground">No roster data.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Roster generation</CardTitle>
                <CardDescription>Current rosters and recent solver runs.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {data.rosters.map((r) => (
                  <Link key={r.id} to={`/rosters/${r.id}`} className="flex items-center justify-between rounded-lg border p-2 hover:bg-muted">
                    <span>{r.name}</span>
                    <span className="flex gap-1"><StatusBadge status={r.status} />
                      {!r.is_valid && <StatusBadge status="ERROR" />}</span>
                  </Link>
                ))}
                <div>
                  <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Recent runs</p>
                  <ul className="space-y-1">
                    {data.recent_runs.map((j) => (
                      <li key={j.id} className="flex items-center justify-between gap-2">
                        <span className="truncate">{j.kind} {j.year}-{String(j.month).padStart(2, '0')}</span>
                        <span className="flex gap-1"><StatusBadge status={j.state} /><StatusBadge status={j.solver_status} /></span>
                      </li>
                    ))}
                    {!data.recent_runs.length && <li className="text-muted-foreground">No runs yet.</li>}
                  </ul>
                </div>
                <Button asChild className="w-full"><Link to="/generate">Generate a roster</Link></Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
