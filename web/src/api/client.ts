// The one place that talks to the API (docs/web.md §3). Relative URLs only, so the same build
// works behind the dev proxy and in production. Auth is postponed (§0); when it comes back, the
// Authorization header and the 401/403 handling go in `request`, and nothing else changes.

const BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Anything thrown → an ApiError, so components only ever deal with one error type. */
export function toApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e))
}

type Envelope<T> =
  | { success: true; data: T }
  | { success: false; error: { code: string; message: string } }

export type Query = Record<string, string | number | boolean | null | undefined>

export function buildUrl(path: string, query: Query = {}): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined) params.set(key, String(value))
  }
  const qs = params.toString()
  return `${BASE}${path}${qs ? `?${qs}` : ''}`
}

export async function request<T>(path: string, query?: Query, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError(0, 'network', 'Sem conexão com a API.')
  }

  let body: Envelope<T>
  try {
    body = (await response.json()) as Envelope<T>
  } catch {
    // A CGI crash or an Apache error page: HTML, not the envelope.
    throw new ApiError(response.status, 'bad_response', `Resposta inesperada da API (HTTP ${response.status}).`)
  }

  if (body.success) return body.data
  throw new ApiError(response.status, body.error.code, body.error.message)
}
