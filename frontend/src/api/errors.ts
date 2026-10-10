export interface ApiErrorOptions {
  code: string
  message: string
  status?: number
  requestId?: string | null
  details?: Record<string, unknown>
  retryAfterSeconds?: number | null
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId: string | null
  readonly details: Record<string, unknown>
  readonly retryAfterSeconds: number | null

  constructor(options: ApiErrorOptions) {
    super(options.message)
    this.name = 'ApiError'
    this.code = options.code
    this.status = options.status ?? 0
    this.requestId = options.requestId ?? null
    this.details = options.details ?? {}
    this.retryAfterSeconds = options.retryAfterSeconds ?? null
  }

  get retryable() {
    return this.status === 429 || this.status >= 500 || this.code === 'NETWORK_UNAVAILABLE'
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'AbortError'
  ) {
    return new ApiError({ code: 'REQUEST_ABORTED', message: 'The request was cancelled.' })
  }
  // Deliberately omit transport error messages/URLs and response bodies.
  return new ApiError({
    code: 'NETWORK_UNAVAILABLE',
    message: 'The local API is unavailable. Your inputs have been retained.',
  })
}
