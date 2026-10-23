import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errorMessage } from '@/services/api'

/** A mutation that refreshes the given queries and reports success/failure as a toast. */
export function useApiMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { invalidate?: QueryKey[]; success?: string | ((r: TResult) => string); silentError?: boolean } = {},
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await Promise.all((opts.invalidate ?? []).map((key) => qc.invalidateQueries({ queryKey: key })))
      const msg = typeof opts.success === 'function' ? opts.success(result) : opts.success
      if (msg) toast.success(msg)
    },
    onError: (err) => {
      if (!opts.silentError) toast.error(errorMessage(err))
    },
  })
}
