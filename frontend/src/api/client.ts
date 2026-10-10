import type {
  Analysis,
  Scenarios,
  TripInput,
  WeatherFrame,
  WeatherVariable,
} from '../contracts/types'
import { ApiError, toApiError } from './errors'
import { isAnalysis, isRecord, isScenarios, isWeatherFrame } from './validation'
import { getAssessmentAccessCode } from './access'

export interface AnalysisApi {
  getExample(scenario: TripInput['scenario'], signal?: AbortSignal): Promise<Analysis>
  getScenarios(signal?: AbortSignal): Promise<Scenarios>
  createAnalysis(input: TripInput, signal?: AbortSignal): Promise<Analysis>
  getAnalysis(id: string, signal?: AbortSignal): Promise<Analysis>
  getFrame(
    id: string,
    hour: number,
    variable: WeatherVariable,
    signal?: AbortSignal,
  ): Promise<WeatherFrame>
}

type Validator<T> = (value: unknown) => value is T
const invalidResponse = () =>
  new ApiError({
    code: 'INVALID_RESPONSE',
    message: 'The API returned an inconsistent response. No new result has been displayed.',
  })
const validId = (id: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)

export class AtlasApi implements AnalysisApi {
  private readonly base: string
  private readonly fetcher: typeof fetch

  constructor(
    base = import.meta.env.VITE_API_BASE ?? '/api/v1',
    fetcher: typeof fetch = (...args) => fetch(...args),
  ) {
    let valid = /^\/(?!\/)/.test(base) && !/[?#]/.test(base)
    if (!valid) {
      try {
        const url = new URL(base)
        valid =
          url.protocol === 'https:' &&
          !url.username &&
          !url.password &&
          !url.search &&
          !url.hash &&
          /^\/api\/v1\/?$/.test(url.pathname)
      } catch {
        /* Reject malformed configuration without logging it. */
      }
    }
    if (!valid)
      throw new Error('API base must be a same-origin path or an explicit HTTPS /api/v1 endpoint.')
    this.base = base.replace(/\/$/, '')
    this.fetcher = fetcher
  }

  private async request<T>(
    path: string,
    validator: Validator<T>,
    options: { signal?: AbortSignal; body?: TripInput | { text: string } } = {},
  ): Promise<T> {
    const timeout = new AbortController()
    const timer = setTimeout(() => timeout.abort(), options.body ? 150_000 : 90_000)
    try {
      const response = await this.fetcher(`${this.base}${path}`, {
        method: options.body ? 'POST' : 'GET',
        headers: {
          Accept: 'application/json',
          ...(getAssessmentAccessCode()
            ? { Authorization: `Bearer ${getAssessmentAccessCode()}` }
            : {}),
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        },
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        signal: options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal,
        ...(options.body ? { body: JSON.stringify(options.body) } : {}),
      })
      let value: unknown
      try {
        value = await response.json()
      } catch {
        throw new ApiError({
          code: 'INVALID_RESPONSE',
          status: response.status,
          message:
            'The backend is not ready or returned an unreadable response. A free service may need about a minute to wake. Your inputs are retained; retry manually.',
        })
      }
      if (!response.ok) {
        const body = isRecord(value) && isRecord(value.error) ? value.error : {}
        const retryHeader = response.headers.get('Retry-After')
        const retryAfter =
          retryHeader !== null && /^\d+$/.test(retryHeader) ? Number(retryHeader) : null
        throw new ApiError({
          status: response.status,
          code: typeof body.code === 'string' ? body.code : 'HTTP_ERROR',
          message:
            typeof body.message === 'string'
              ? body.message
              : 'The local API could not complete the request.',
          details: isRecord(body.details) ? body.details : {},
          requestId:
            isRecord(value) && typeof value.request_id === 'string' ? value.request_id : null,
          retryAfterSeconds: retryAfter,
        })
      }
      if (!validator(value)) throw invalidResponse()
      return value
    } catch (error) {
      if (timeout.signal.aborted && !options.signal?.aborted)
        throw new ApiError({
          code: 'BACKEND_TIMEOUT',
          message:
            'The backend took too long. It may still be processing. No automatic analysis retry was made.',
          status: 504,
        })
      throw toApiError(error)
    } finally {
      clearTimeout(timer)
    }
  }

  getHealth(signal?: AbortSignal) {
    return this.request(
      '/health/',
      (value): value is { assessment_access_required: boolean; live_available: boolean } =>
        isRecord(value) &&
        value.status === 'ok' &&
        typeof value.assessment_access_required === 'boolean' &&
        typeof value.live_available === 'boolean',
      signal ? { signal } : {},
    )
  }

  getScenarios(signal?: AbortSignal) {
    return this.request('/scenarios/', isScenarios, signal ? { signal } : {})
  }
  async getExample(scenario: TripInput['scenario'], signal?: AbortSignal) {
    if (!['complete', 'partial', 'no-travel'].includes(scenario))
      throw new ApiError({ code: 'INVALID_ARGUMENT', message: 'Choose an available example trip.' })
    const result = await this.request(
      `/examples/${scenario}/`,
      isAnalysis,
      signal ? { signal } : {},
    )
    if (result.mode !== 'sample' || !result.sample_data || result.scenario !== scenario)
      throw invalidResponse()
    return result
  }
  geocode(text: string) {
    return this.request(
      '/locations/geocode/',
      (value): value is GeocodePlace[] =>
        Array.isArray(value) &&
        value.every(
          (item) =>
            isRecord(item) &&
            typeof item.name === 'string' &&
            typeof item.latitude === 'string' &&
            typeof item.longitude === 'string' &&
            Number.isFinite(Number(item.latitude)) &&
            Number.isFinite(Number(item.longitude)),
        ),
      { body: { text } },
    )
  }
  createAnalysis(input: TripInput, signal?: AbortSignal) {
    return this.request('/analyses/', isAnalysis, { body: input, ...(signal ? { signal } : {}) })
  }
  async getAnalysis(id: string, signal?: AbortSignal) {
    if (!validId(id))
      throw new ApiError({
        code: 'INVALID_ARGUMENT',
        message: 'The analysis identifier is invalid.',
      })
    const result = await this.request(
      `/analyses/${encodeURIComponent(id)}/`,
      isAnalysis,
      signal ? { signal } : {},
    )
    if (result.id !== id) throw invalidResponse()
    return result
  }
  async getFrame(id: string, hour: number, variable: WeatherVariable, signal?: AbortSignal) {
    if (
      !validId(id) ||
      !Number.isInteger(hour) ||
      hour < 0 ||
      hour > 48 ||
      !['wind', 'rain', 'snow'].includes(variable)
    ) {
      throw new ApiError({
        code: 'INVALID_ARGUMENT',
        message: 'Select an existing analysis, hour 0–48 and a weather field.',
      })
    }
    const query = new URLSearchParams({ hour: String(hour), variable })
    const result = await this.request(
      `/analyses/${encodeURIComponent(id)}/frames/?${query}`,
      isWeatherFrame,
      signal ? { signal } : {},
    )
    if (result.analysis_id !== id || result.hour !== hour || result.variable !== variable)
      throw invalidResponse()
    return result
  }
}

export const atlasApi = new AtlasApi()

export interface GeocodePlace {
  name: string
  latitude: string
  longitude: string
  timezone?: string | null
  entry_points?: { latitude: string; longitude: string }[]
}
