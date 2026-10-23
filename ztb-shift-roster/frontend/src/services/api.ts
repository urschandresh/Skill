// Thin fetch client for the local ShiftOrbit API. Every state-changing call carries the
// X-ZTB-Request header the backend requires (see backend/app/security.py).

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(formatDetail(detail) || `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

export function formatDetail(detail: unknown): string {
  if (detail == null) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? (d as { loc: unknown[] }).loc.filter((x) => x !== 'body').join('.')
            : ''
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg
        }
        return String(d)
      })
      .join('; ')
  }
  if (typeof detail === 'object' && 'message' in (detail as object)) {
    return String((detail as { message: unknown }).message)
  }
  return JSON.stringify(detail)
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  let payload: BodyInit | undefined
  if (method !== 'GET') headers['X-ZTB-Request'] = '1'
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload, credentials: 'same-origin' })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      detail = (await res.json()).detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') ?? ''
  if (type.includes('application/json')) return (await res.json()) as T
  return (await res.blob()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  del: <T = void>(path: string) => request<T>('DELETE', path),
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return String(err)
}

/** Download a file produced by a GET endpoint without exposing it to any third party. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`/api${path}`, { credentials: 'same-origin' })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      detail = (await res.json()).detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  const blob = await res.blob()
  const disposition = res.headers.get('content-disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = match?.[1] ?? fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
