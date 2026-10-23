import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorAlert, Loading, NativeSelect, PageHeader, StatusBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { MONTHS } from '@/lib/roster'
import { useProjects, useRosters } from '@/services/queries'

export function RostersPage() {
  const [status, setStatus] = useState('')
  const { data, isLoading, error } = useRosters({ status: status || undefined })
  const { data: projects = [] } = useProjects()
  const code = new Map(projects.map((p) => [p.id, p.code]))
  return (
    <div>
      <PageHeader title="Rosters" description="Every version: drafts, the published roster per month, archived and imported historical rosters."
        actions={<Button asChild><Link to="/generate"><Plus /> Generate</Link></Button>} />
      <NativeSelect aria-label="Status filter" className="mb-4 w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>
        {['draft', 'published', 'archived', 'historical'].map((s) => <option key={s} value={s}>{s}</option>)}
      </NativeSelect>
      <ErrorAlert error={error} />
      {isLoading && <Loading />}
      {data && !data.length && <EmptyState title="No rosters yet">Use the generator or import a historical roster.</EmptyState>}
      {!!data?.length && (
        <Card className="py-0">
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Month</TableHead><TableHead>Name</TableHead><TableHead>Status</TableHead>
                  <TableHead>Solver</TableHead><TableHead>Projects</TableHead>
                  <TableHead className="text-right">Assignments</TableHead><TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{MONTHS[r.month - 1]} {r.year}</TableCell>
                    <TableCell><Link className="text-primary hover:underline" to={`/rosters/${r.id}`}>{r.name}</Link></TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell><StatusBadge status={r.solver_status} /></TableCell>
                    <TableCell>{r.project_ids.map((p) => code.get(p) ?? p).join(', ')}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.assignment_count}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{new Date(r.updated_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
