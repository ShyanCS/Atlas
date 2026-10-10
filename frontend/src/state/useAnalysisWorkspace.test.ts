import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AnalysisApi } from '../api/client'
import { ApiError } from '../api/errors'
import { createSampleInput } from '../contracts/input'
import type { Analysis, WeatherFrame } from '../contracts/types'
import {
  completeAnalysis,
  mixedEligibilityAnalysis,
  noTravelAnalysis,
  scenariosFixture,
  windFrame,
} from '../test/fixtures'
import { useAnalysisWorkspace } from './useAnalysisWorkspace'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function mockApi() {
  return {
    getExample: vi.fn<AnalysisApi['getExample']>().mockResolvedValue(completeAnalysis),
    getScenarios: vi.fn<AnalysisApi['getScenarios']>().mockResolvedValue(scenariosFixture),
    createAnalysis: vi.fn<AnalysisApi['createAnalysis']>().mockResolvedValue(completeAnalysis),
    getAnalysis: vi.fn<AnalysisApi['getAnalysis']>().mockResolvedValue(completeAnalysis),
    getFrame: vi.fn<AnalysisApi['getFrame']>().mockResolvedValue(windFrame),
  }
}
function frameAt(hour: number): WeatherFrame {
  const instant = new Date(Date.parse(windFrame.requested_at) + hour * 3_600_000).toISOString()
  return {
    ...windFrame,
    hour,
    requested_at: instant,
    cells: windFrame.cells.map((cell) => ({
      ...cell,
      measurement: {
        ...cell.measurement,
        provenance: { ...cell.measurement.provenance, valid_at: instant },
      },
    })),
  }
}

describe('workspace async lifecycle', () => {
  it('discards unsubmitted edits without rerouting or altering the committed analysis', async () => {
    const client = mockApi()
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await act(async () => {
      await result.current.analyze(createSampleInput(scenariosFixture))
    })
    act(() => result.current.markStale())
    expect(result.current.state.isStale).toBe(true)
    act(() => result.current.discardDraft())
    expect(result.current.state.isStale).toBe(false)
    expect(result.current.state.analysis).toBe(completeAnalysis)
    expect(client.createAnalysis).toHaveBeenCalledTimes(1)
  })
  it('loads scenario defaults and returns success without changing the snapshot on selection', async () => {
    const client = mockApi()
    client.createAnalysis.mockResolvedValueOnce(mixedEligibilityAnalysis)
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await waitFor(() => expect(result.current.loadingScenarios).toBe(false))
    expect(result.current.scenarios).toBe(scenariosFixture)
    let returned: Analysis | null = null
    await act(async () => {
      returned = await result.current.analyze(createSampleInput(scenariosFixture))
    })
    expect(returned).toBe(mixedEligibilityAnalysis)
    const blocked = mixedEligibilityAnalysis.routes.find((route) => !route.eligible)!
    act(() => result.current.selectRoute(blocked.id))
    expect(result.current.state.analysis?.recommendation).toBe(
      mixedEligibilityAnalysis.recommendation,
    )
    expect(result.current.state.selectedRouteId).toBe(blocked.id)
  })

  it('retains the previous result and returns null on a blocked actual-mode request', async () => {
    const client = mockApi()
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await act(async () => {
      await result.current.analyze(createSampleInput(scenariosFixture))
    })
    client.createAnalysis.mockRejectedValueOnce(
      new ApiError({
        code: 'LIVE_MODE_UNAVAILABLE',
        status: 503,
        message: 'Actual mode unavailable.',
      }),
    )
    let returned: Analysis | null = completeAnalysis
    await act(async () => {
      returned = await result.current.analyze({
        ...createSampleInput(scenariosFixture),
        mode: 'actual',
      })
    })
    expect(returned).toBeNull()
    expect(result.current.state.analysis).toBe(completeAnalysis)
    expect(result.current.state.isStale).toBe(true)
    expect(result.current.error?.code).toBe('LIVE_MODE_UNAVAILABLE')
    expect(client.createAnalysis).toHaveBeenCalledTimes(2)
  })

  it('rejects late frames even when a transport ignores cancellation', async () => {
    const client = mockApi()
    const first = deferred<WeatherFrame>()
    const second = deferred<WeatherFrame>()
    client.getFrame.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await act(async () => {
      await result.current.analyze(createSampleInput(scenariosFixture))
    })
    let firstResult!: Promise<WeatherFrame | null>
    act(() => {
      firstResult = result.current.requestFrame(0, 'wind')
    })
    act(() => {
      void result.current.requestFrame(1, 'wind')
    })
    expect(client.getFrame.mock.calls[0]?.[3]?.aborted).toBe(true)
    await act(async () => {
      second.resolve(frameAt(1))
      await second.promise
    })
    expect(result.current.state.displayedFrame?.hour).toBe(1)
    await act(async () => {
      first.resolve(windFrame)
      await first.promise
    })
    expect(await firstResult).toBeNull()
    expect(result.current.state.displayedFrame?.hour).toBe(1)
  })

  it('changes run while a frame is in flight without showing the previous run frame', async () => {
    const client = mockApi()
    const pending = deferred<WeatherFrame>()
    client.getFrame.mockReturnValueOnce(pending.promise)
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await act(async () => {
      await result.current.analyze(createSampleInput(scenariosFixture))
    })
    act(() => {
      void result.current.requestFrame(0, 'wind')
    })
    client.createAnalysis.mockResolvedValueOnce(noTravelAnalysis)
    await act(async () => {
      await result.current.analyze({
        ...createSampleInput(scenariosFixture),
        scenario: 'no-travel',
      })
    })
    await act(async () => {
      pending.resolve(windFrame)
      await pending.promise
    })
    expect(result.current.state.analysis).toBe(noTravelAnalysis)
    expect(result.current.state.displayedFrame).toBeNull()
    expect(result.current.state.analysis?.recommendation.route_id).toBeNull()
  })

  it('does not mark an in-flight result current after the user edits the draft', async () => {
    const client = mockApi()
    const pending = deferred<Analysis>()
    client.createAnalysis.mockReturnValueOnce(pending.promise)
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    act(() => {
      void result.current.analyze(createSampleInput(scenariosFixture))
    })
    act(() => result.current.markStale())
    await act(async () => {
      pending.resolve(completeAnalysis)
      await pending.promise
    })
    expect(result.current.state.isStale).toBe(true)
  })

  it('recovers scenario retrieval without clearing an existing analysis', async () => {
    const client = mockApi()
    client.getScenarios.mockRejectedValueOnce(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'Local API unavailable.' }),
    )
    const { result } = renderHook(() => useAnalysisWorkspace(client))
    await waitFor(() => expect(result.current.loadingScenarios).toBe(false))
    expect(result.current.error?.code).toBe('NETWORK_UNAVAILABLE')
    await act(async () => {
      await result.current.analyze(createSampleInput(scenariosFixture))
      await result.current.reloadScenarios()
    })
    expect(result.current.scenarios).toBe(scenariosFixture)
    expect(result.current.state.analysis).toBe(completeAnalysis)
    expect(result.current.error).toBeNull()
  })

  it('aborts in-flight work on unmount', () => {
    const client = mockApi()
    client.getScenarios.mockReturnValueOnce(deferred<typeof scenariosFixture>().promise)
    const { unmount } = renderHook(() => useAnalysisWorkspace(client))
    const signal = client.getScenarios.mock.calls[0]?.[0]
    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
