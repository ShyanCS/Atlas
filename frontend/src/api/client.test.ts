import { describe, expect, it, vi } from 'vitest'
import { AtlasApi } from './client'
import { ApiError } from './errors'
import { completeAnalysis, missingSnowFrame, scenariosFixture, windFrame } from '../test/fixtures'
import { createSampleInput } from '../contracts/input'

const json = (value: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })

describe('typed API boundary', () => {
  it('reads the authored scenario contract and serializes decimal inputs without conversion', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(scenariosFixture))
      .mockResolvedValueOnce(json(completeAnalysis, 201))
    const client = new AtlasApi('/api/v1', fetcher)
    const scenarios = await client.getScenarios()
    const input = createSampleInput(scenarios)
    await client.createAnalysis({ ...input, load_weight_lb: '30000.01' })
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/scenarios/')
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body)).load_weight_lb).toBe('30000.01')
    expect(fetcher.mock.calls[1]?.[1]?.credentials).toBe('omit')
  })

  it('surfaces structured actual-mode errors with no fallback/retry', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        {
          error: {
            code: 'LIVE_MODE_UNAVAILABLE',
            message: 'Actual mode is unavailable.',
            details: {},
          },
          request_id: 'sample-request-id',
        },
        503,
      ),
    )
    const client = new AtlasApi('/api/v1', fetcher)
    await expect(
      client.createAnalysis({ ...createSampleInput(scenariosFixture), mode: 'actual' }),
    ).rejects.toMatchObject({
      code: 'LIVE_MODE_UNAVAILABLE',
      status: 503,
      requestId: 'sample-request-id',
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('keeps Retry-After and validation details for honest recovery', async () => {
    expect.assertions(2)
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        {
          error: {
            code: 'RATE_LIMITED',
            message: 'Pause new requests.',
            details: { retry: ['Later'] },
          },
        },
        429,
        { 'Retry-After': '60' },
      ),
    )
    try {
      await new AtlasApi('/api/v1', fetcher).getScenarios()
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect(error).toMatchObject({
        retryAfterSeconds: 60,
        details: { retry: ['Later'] },
        retryable: true,
      })
    }
  })

  it('rejects wrong-run/hour frame responses and accepts explicitly missing snow', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ ...windFrame, analysis_id: 'wrong' }))
      .mockResolvedValueOnce(json(missingSnowFrame))
    const client = new AtlasApi('/api/v1', fetcher)
    await expect(client.getFrame(completeAnalysis.id, 0, 'wind')).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    })
    const missing = await client.getFrame(completeAnalysis.id, 48, 'snow')
    expect(missing.acquisition_status).toBe('missing')
    expect(missing.cells.every((cell) => cell.measurement.value === null)).toBe(true)
  })

  it('rejects malformed identity/measurement data rather than displaying a result', async () => {
    const broken = structuredClone(completeAnalysis)
    broken.routes[0]!.checkpoints[0]!.measurements.wind.value = 'not-a-number'
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(broken))
    await expect(
      new AtlasApi('/api/v1', fetcher).createAnalysis(createSampleInput(scenariosFixture)),
    ).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('preserves exact scientific decimal strings from the canonical API', async () => {
    const source = structuredClone(completeAnalysis)
    source.routes[0]!.exposure.unknown_mi = '0E+3'
    source.routes[0]!.checkpoints[0]!.measurements.rain.value = '1.000000000000000000001E-8'
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(source, 201))
    const result = await new AtlasApi('/api/v1', fetcher).createAnalysis(
      createSampleInput(scenariosFixture),
    )
    expect(result.routes[0]!.exposure.unknown_mi).toBe('0E+3')
    expect(result.routes[0]!.checkpoints[0]!.measurements.rain.value).toBe(
      '1.000000000000000000001E-8',
    )
  })

  it('rejects out-of-range arguments without any HTTP request', async () => {
    const fetcher = vi.fn<typeof fetch>()
    const client = new AtlasApi('/api/v1', fetcher)
    await expect(client.getFrame(completeAnalysis.id, 49, 'wind')).rejects.toMatchObject({
      code: 'INVALID_ARGUMENT',
    })
    await expect(client.getAnalysis('../other')).rejects.toMatchObject({ code: 'INVALID_ARGUMENT' })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('does not expose transport URLs, HTML bodies or secrets in error messages', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('https://provider.invalid/?key=secret'))
      .mockResolvedValueOnce(new Response('<html>private-secret</html>', { status: 502 }))
    const client = new AtlasApi('/api/v1', fetcher)
    await expect(client.getScenarios()).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
      message: expect.not.stringContaining('secret'),
    })
    await expect(client.getScenarios()).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
      message: expect.not.stringContaining('secret'),
    })
    expect(() => new AtlasApi('https://external.invalid')).toThrow('same-origin')
  })
})
