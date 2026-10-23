import { AlertTriangle, CheckCircle2, Info, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { readableText } from '@/lib/roster'
import { cn } from '@/lib/utils'
import { errorMessage } from '@/services/api'
import type { Violation } from '@/types/api'

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function StatCard({ label, value, hint, icon, tone = 'default' }: {
  label: string
  value: ReactNode
  hint?: string
  icon?: ReactNode
  tone?: 'default' | 'warn' | 'good'
}) {
  return (
    <Card className="gap-2 py-4">
      <CardContent className="flex items-start justify-between gap-3 px-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className={cn('mt-1 text-2xl font-semibold',
            tone === 'warn' && 'text-amber-400', tone === 'good' && 'text-emerald-400')}>{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        {icon && <div className="rounded-lg bg-primary/15 p-2 text-primary">{icon}</div>}
      </CardContent>
    </Card>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground" role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  )
}

export function ErrorAlert({ error, title = 'Something went wrong' }: { error: unknown; title?: string }) {
  if (!error) return null
  return (
    <Alert variant="destructive" className="my-3">
      <AlertTriangle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
    </Alert>
  )
}

export function InfoAlert({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Alert className="my-3">
      <Info />
      <AlertTitle>{title}</AlertTitle>
      {children && <AlertDescription>{children}</AlertDescription>}
    </Alert>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}

export function ShiftChip({ code, color, label, locked, title, className }: {
  code: string
  color: string
  label?: string
  locked?: boolean
  title?: string
  className?: string
}) {
  return (
    <span
      title={title}
      className={cn('inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] font-semibold leading-none',
        locked && 'ring-2 ring-white/80', className)}
      style={{ backgroundColor: color, color: readableText(color) }}
    >
      {label ? `${label}:` : ''}{code}{locked ? ' 🔒' : ''}
    </span>
  )
}

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-sky-500/15 text-sky-300',
  published: 'bg-emerald-500/15 text-emerald-300',
  archived: 'bg-slate-500/20 text-slate-300',
  historical: 'bg-violet-500/15 text-violet-300',
  pending: 'bg-amber-500/15 text-amber-300',
  approved: 'bg-emerald-500/15 text-emerald-300',
  rejected: 'bg-rose-500/15 text-rose-300',
  cancelled: 'bg-slate-500/20 text-slate-300',
  OPTIMAL: 'bg-emerald-500/15 text-emerald-300',
  FEASIBLE: 'bg-sky-500/15 text-sky-300',
  INFEASIBLE: 'bg-rose-500/15 text-rose-300',
  TIMEOUT: 'bg-amber-500/15 text-amber-300',
  CANCELLED: 'bg-slate-500/20 text-slate-300',
  ERROR: 'bg-rose-500/15 text-rose-300',
  running: 'bg-sky-500/15 text-sky-300',
  queued: 'bg-slate-500/20 text-slate-300',
  completed: 'bg-emerald-500/15 text-emerald-300',
  failed: 'bg-rose-500/15 text-rose-300',
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null
  return <Badge className={cn('border-0', STATUS_STYLES[status] ?? 'bg-muted text-foreground')}>{status}</Badge>
}

export function ViolationList({ violations, max = 50, empty = 'No rule violations.' }: {
  violations: Violation[]
  max?: number
  empty?: string
}) {
  if (!violations.length) {
    return (
      <p className="flex items-center gap-2 text-sm text-emerald-400">
        <CheckCircle2 className="size-4" /> {empty}
      </p>
    )
  }
  return (
    <ul className="space-y-1 text-sm">
      {violations.slice(0, max).map((v, i) => (
        <li key={i} className="flex gap-2">
          <Badge className={cn('h-5 shrink-0 border-0',
            v.severity === 'error' ? 'bg-rose-500/20 text-rose-300' : 'bg-amber-500/20 text-amber-300')}>
            {v.rule}
          </Badge>
          <span>{v.message}</span>
        </li>
      ))}
      {violations.length > max && <li className="text-muted-foreground">…and {violations.length - max} more</li>}
    </ul>
  )
}

export function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-rose-400">{message}</p> : null
}

export function Field({ label, htmlFor, error, children, hint }: {
  label: string
  htmlFor?: string
  error?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      <FieldError message={error} />
    </div>
  )
}

/** A native select styled like the shadcn input: simple, accessible and easy to test. */
export function NativeSelect({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn('h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none',
        'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 [&>option]:bg-popover',
        className)}
      {...props}
    />
  )
}
