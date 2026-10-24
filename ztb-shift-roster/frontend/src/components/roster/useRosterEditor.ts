import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import { emptyHistory, recordBatch, redoStep, undoStep, type History } from '@/lib/roster'
import { ApiError, api, errorMessage } from '@/services/api'
import { keys } from '@/services/queries'
import type { ChangeResult, RosterOp, Violation } from '@/types/api'

export interface PendingChange {
  ops: RosterOp[]
  introduced: Violation[]
  resolved: Violation[]
  after?: History
  label: string
}

/**
 * Every edit is validated by the backend before it is saved: a dry run first, then a commit
 * if it introduces no rule violations. Otherwise the user sees the violations and may
 * confirm with a written reason (recorded on the assignment).
 */
export function useRosterEditor(rosterId: number) {
  const qc = useQueryClient()
  const [history, setHistory] = useState<History>(emptyHistory)
  const [pending, setPending] = useState<PendingChange | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: keys.roster(rosterId) }),
      qc.invalidateQueries({ queryKey: keys.validation(rosterId) }),
    ])
  }, [qc, rosterId])

  const commit = useCallback(async (ops: RosterOp[], reason: string | null, after: History) => {
    setBusy(true)
    try {
      await api.post<ChangeResult>(`/rosters/${rosterId}/changes`, { ops, override_reason: reason })
      setHistory(after)
      setPending(null)
      await refresh()
      toast.success(reason ? 'Change saved with override' : 'Change saved')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }, [rosterId, refresh])

  const run = useCallback(async (ops: RosterOp[], after: History, label: string) => {
    setBusy(true)
    try {
      const dry = await api.post<ChangeResult>(`/rosters/${rosterId}/changes`, { ops, dry_run: true })
      if (dry.introduced.length === 0) {
        setBusy(false)
        await commit(ops, null, after)
        return
      }
      setPending({ ops, introduced: dry.introduced, resolved: dry.resolved, after, label })
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : errorMessage(err)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }, [rosterId, commit])

  const apply = useCallback((ops: RosterOp[], label = 'Change') => run(ops, recordBatch(history, ops), label),
    [run, history])

  const undo = useCallback(() => {
    const step = undoStep(history)
    if (step) void run(step.ops, step.next, 'Undo')
  }, [history, run])

  const redo = useCallback(() => {
    const step = redoStep(history)
    if (step) void run(step.ops, step.next, 'Redo')
  }, [history, run])

  const resetHistory = useCallback(() => setHistory(emptyHistory), [])
  const dismissPending = useCallback(() => setPending(null), [])

  return {
    apply, undo, redo, busy, pending, resetHistory, dismissPending,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    confirmPending: (reason: string) => pending && commit(pending.ops, reason, pending.after ?? history),
  }
}
