import { Download, FileUp, Upload } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { ErrorAlert, Field, InfoAlert, NativeSelect, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { MONTHS } from '@/lib/roster'
import { api, downloadFile, errorMessage } from '@/services/api'
import { useProjects, useRosters } from '@/services/queries'

type Kind = 'analysts' | 'leave' | 'roster'

interface PreviewField { name: string; required: boolean; description: string }
interface Preview {
  token: string
  kind: Kind
  filename: string
  sheets: string[]
  sheet: string | null
  columns: string[]
  rows: (string | null)[][]
  row_count: number
  fields: PreviewField[]
  suggested_mapping: Record<string, string | null>
  detected: Record<string, unknown>
  errors: string[]
  warnings: string[]
}
interface CommitResult {
  created: number
  updated: number
  skipped: number
  errors: { row: number | null; message: string }[]
  roster_id?: number | null
  message: string
}

const KIND_HELP: Record<Kind, string> = {
  analysts: 'One row per analyst: employee code, name, optional email, eligible project codes and skills.',
  leave: 'One row per leave: employee code, start date, end date, type, status (approved or pending), optional times for partial days.',
  roster: 'A monthly roster: a ShiftOrbit export, or the previous SOC roster format (analysts in rows, one column per day, codes like M, A, N, WO, LEAVE, H).',
}

export function ImportExportPage() {
  const rosters = useRosters()
  const { data: projects = [] } = useProjects()
  const [exportId, setExportId] = useState('')
  const [kind, setKind] = useState<Kind>('analysts')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [opts, setOpts] = useState(() => ({ year: new Date().getFullYear(), month: new Date().getMonth() + 1, project_id: '',
    status: 'historical', create_missing_analysts: false, update_existing: false }))
  const [result, setResult] = useState<CommitResult | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const doPreview = async (sheet?: string) => {
    if (!file) return
    setBusy(true); setError(null); setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('kind', kind)
      if (sheet) fd.append('sheet', sheet)
      const p = await api.post<Preview>('/imports/preview', fd)
      setPreview(p)
      setMapping(p.suggested_mapping)
      const det = p.detected as { year?: number; month?: number }
      if (det.year && det.month) setOpts((o) => ({ ...o, year: det.year!, month: det.month! }))
    } catch (e) { setError(e); setPreview(null) }
    setBusy(false)
  }
  const commit = async () => {
    if (!preview) return
    setBusy(true); setError(null)
    try {
      const r = await api.post<CommitResult>('/imports/commit', { token: preview.token, mapping, options: {
        ...opts, project_id: opts.project_id ? Number(opts.project_id) : null } })
      setResult(r)
      toast.success(r.message)
    } catch (e) { setError(e) }
    setBusy(false)
  }

  return (
    <div>
      <PageHeader title="Import / Export" description="Excel (XLSX) and CSV, processed locally. Files never leave this computer." />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Export roster</CardTitle>
            <CardDescription>Editable XLSX: Monthly Roster, Project Coverage, Leave Register, Workload Summary, Shift Legend, Validation Report, Configuration.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <NativeSelect aria-label="Roster to export" value={exportId} onChange={(e) => setExportId(e.target.value)}>
              <option value="">Choose roster…</option>
              {rosters.data?.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.status})</option>)}
            </NativeSelect>
            <Button disabled={!exportId} onClick={() => downloadFile(`/rosters/${exportId}/export.xlsx`, 'roster.xlsx').catch((e) => toast.error(errorMessage(e)))}>
              <Download /> Download XLSX
            </Button>
            <div className="border-t pt-3">
              <p className="mb-2 text-sm font-medium">Import templates</p>
              <div className="flex flex-wrap gap-2">
                {(['analysts', 'leave'] as const).map((k) => (
                  <Button key={k} size="sm" variant="outline"
                    onClick={() => downloadFile(`/imports/templates/${k}.xlsx`, `${k}-template.xlsx`).catch((e) => toast.error(errorMessage(e)))}>
                    <Download /> {k}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Import</CardTitle>
            <CardDescription>Upload, preview, map columns, validate, then commit. Nothing is saved until you commit.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="What are you importing?" htmlFor="imp-kind">
                <NativeSelect id="imp-kind" value={kind} onChange={(e) => { setKind(e.target.value as Kind); setPreview(null); setResult(null) }}>
                  <option value="analysts">Analysts</option>
                  <option value="leave">Leave</option>
                  <option value="roster">Roster (historical or ShiftOrbit export)</option>
                </NativeSelect>
              </Field>
              <Field label="File (.xlsx or .csv, max 5 MB)" htmlFor="imp-file">
                <Input id="imp-file" type="file" accept=".xlsx,.csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); setResult(null) }} />
              </Field>
              <div className="flex items-end">
                <Button onClick={() => doPreview()} disabled={!file || busy}><FileUp /> Preview</Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{KIND_HELP[kind]}</p>
            <ErrorAlert error={error} />

            {preview && (
              <div className="space-y-4" data-testid="import-preview">
                {preview.sheets.length > 1 && (
                  <Field label="Sheet" htmlFor="imp-sheet">
                    <NativeSelect id="imp-sheet" value={preview.sheet ?? ''} onChange={(e) => doPreview(e.target.value)}>
                      {preview.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                    </NativeSelect>
                  </Field>
                )}
                {preview.errors.map((e, i) => <p key={i} className="text-sm text-rose-300">{e}</p>)}
                {preview.warnings.map((w, i) => <p key={i} className="text-sm text-amber-300">{w}</p>)}

                {preview.fields.length > 0 && (
                  <div>
                    <p className="mb-2 text-sm font-medium">Column mapping</p>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {preview.fields.map((f) => (
                        <Field key={f.name} label={`${f.name}${f.required ? ' *' : ''}`} htmlFor={`map-${f.name}`} hint={f.description}>
                          <NativeSelect id={`map-${f.name}`} value={mapping[f.name] ?? ''}
                            onChange={(e) => setMapping({ ...mapping, [f.name]: e.target.value || null })}>
                            <option value="">— not in file —</option>
                            {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                          </NativeSelect>
                        </Field>
                      ))}
                    </div>
                  </div>
                )}

                {preview.kind === 'roster' && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label="Month" htmlFor="imp-month">
                      <NativeSelect id="imp-month" value={opts.month} onChange={(e) => setOpts({ ...opts, month: Number(e.target.value) })}>
                        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                      </NativeSelect>
                    </Field>
                    <Field label="Year" htmlFor="imp-year">
                      <Input id="imp-year" inputMode="numeric" value={opts.year} onChange={(e) => setOpts({ ...opts, year: Number(e.target.value) || 0 })} />
                    </Field>
                    <Field label="Project for codes without a project prefix" htmlFor="imp-project">
                      <NativeSelect id="imp-project" value={opts.project_id} onChange={(e) => setOpts({ ...opts, project_id: e.target.value })}>
                        <option value="">Choose…</option>
                        {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
                      </NativeSelect>
                    </Field>
                    <Field label="Save as" htmlFor="imp-status">
                      <NativeSelect id="imp-status" value={opts.status} onChange={(e) => setOpts({ ...opts, status: e.target.value })}>
                        <option value="historical">Historical roster (read-only reference, month continuity)</option>
                        <option value="draft">Draft roster (editable)</option>
                      </NativeSelect>
                    </Field>
                    <label className="flex items-center gap-2 text-sm sm:col-span-2">
                      <Checkbox checked={opts.create_missing_analysts} onCheckedChange={(c) => setOpts({ ...opts, create_missing_analysts: !!c })} />
                      Create analysts that do not exist yet (eligible for the chosen project)
                    </label>
                  </div>
                )}
                {preview.kind !== 'roster' && (
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox checked={opts.update_existing} onCheckedChange={(c) => setOpts({ ...opts, update_existing: !!c })} />
                    Update records that already exist (otherwise they are skipped)
                  </label>
                )}

                <div>
                  <p className="mb-1 text-sm font-medium">Preview: first {preview.rows.length} of {preview.row_count} rows</p>
                  <div className="max-h-72 overflow-auto rounded-lg border">
                    <Table>
                      <TableHeader><TableRow>{preview.columns.map((c) => <TableHead key={c}>{c}</TableHead>)}</TableRow></TableHeader>
                      <TableBody>
                        {preview.rows.map((r, i) => (
                          <TableRow key={i}>{r.map((v, j) => <TableCell key={j} className="text-xs">{v}</TableCell>)}</TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
                {Object.keys(preview.detected).length > 0 && (
                  <p className="text-xs text-muted-foreground">Detected: {Object.entries(preview.detected).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`).join(' · ')}</p>
                )}
                <Button onClick={commit} disabled={busy || preview.errors.length > 0}><Upload /> Validate & import</Button>
              </div>
            )}

            {result && (
              <InfoAlert title={result.message}>
                <p>Created {result.created} · updated {result.updated} · skipped {result.skipped}</p>
                {result.roster_id && <p><Link className="text-primary underline" to={`/rosters/${result.roster_id}`}>Open the imported roster</Link></p>}
                {result.errors.length > 0 && (
                  <ul className="mt-2 max-h-48 list-disc overflow-auto pl-5 text-rose-300" data-testid="import-errors">
                    {result.errors.map((e, i) => <li key={i}>{e.row != null ? `Row ${e.row}: ` : ''}{e.message}</li>)}
                  </ul>
                )}
              </InfoAlert>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
