import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/errors'
import {
  completeAnalysis,
  mixedEligibilityAnalysis,
  noTravelAnalysis,
  partialAnalysis,
  windFrame,
} from '../test/fixtures'
import { initialWorkspaceState, workspaceReducer } from './workspace'
import type { WorkspaceState } from './workspace'

function ready(): WorkspaceState {
  return workspaceReducer(
    workspaceReducer(initialWorkspaceState, { type: 'analysis/requested', requestId: 1 }),
    {
      type: 'analysis/received',
      requestId: 1,
      analysis: completeAnalysis,
    },
  )
}

describe('shared analysis selection and provenance', () => {
  it('restores snapshot freshness only when an unsubmitted draft is explicitly discarded', () => {
    const before = ready()
    const changed = workspaceReducer(before, { type: 'draft/changed' })
    const restored = workspaceReducer(changed, { type: 'draft/discarded' })
    expect(restored.isStale).toBe(false)
    expect(restored.analysis).toBe(before.analysis)
    expect(restored.selectedRouteId).toBe(before.selectedRouteId)
  })

  it('cannot discard the draft state of a submitted request that is still pending', () => {
    const pending = workspaceReducer(ready(), { type: 'analysis/requested', requestId: 5 })
    const changed = workspaceReducer(pending, { type: 'draft/changed' })
    expect(workspaceReducer(changed, { type: 'draft/discarded' })).toBe(changed)
  })
  it('selects the backend preference but inspecting a blocked route never changes it', () => {
    const state = { ...ready(), analysis: mixedEligibilityAnalysis }
    const blocked = mixedEligibilityAnalysis.routes.find((route) => !route.eligible)
    expect(blocked).toBeDefined()
    const selected = workspaceReducer(state, { type: 'route/selected', routeId: blocked!.id })
    expect(selected.selectedRouteId).toBe(blocked!.id)
    expect(selected.analysis).toBe(mixedEligibilityAnalysis)
    expect(selected.analysis?.recommendation).toEqual(mixedEligibilityAnalysis.recommendation)
  })

  it('checkpoint selection selects its parent and route change clears incompatible detail', () => {
    const [first, second] = completeAnalysis.routes
    const point = second!.checkpoints[0]!
    const selected = workspaceReducer(ready(), {
      type: 'checkpoint/selected',
      routeId: second!.id,
      checkpointId: point.id,
    })
    expect(selected.selectedRouteId).toBe(second!.id)
    expect(selected.selectedCheckpointId).toBe(point.id)
    expect(
      workspaceReducer(selected, { type: 'route/selected', routeId: first!.id })
        .selectedCheckpointId,
    ).toBeNull()
    expect(
      workspaceReducer(selected, {
        type: 'checkpoint/selected',
        routeId: first!.id,
        checkpointId: point.id,
      }),
    ).toBe(selected)
  })

  it('rejects stale analysis completion and retains changed drafts as stale', () => {
    const first = workspaceReducer(ready(), { type: 'analysis/requested', requestId: 2 })
    const second = workspaceReducer(first, { type: 'analysis/requested', requestId: 3 })
    expect(
      workspaceReducer(second, {
        type: 'analysis/received',
        requestId: 2,
        analysis: partialAnalysis,
      }),
    ).toBe(second)
    const edited = workspaceReducer(second, { type: 'draft/changed' })
    const arrived = workspaceReducer(edited, {
      type: 'analysis/received',
      requestId: 3,
      analysis: partialAnalysis,
    })
    expect(arrived.isStale).toBe(true)
    expect(arrived.analysis).toBe(partialAnalysis)
  })

  it('retains old snapshot and selection after validation/provider failure', () => {
    const before = ready()
    const pending = workspaceReducer(before, { type: 'analysis/requested', requestId: 2 })
    const error = new ApiError({
      code: 'LIVE_MODE_UNAVAILABLE',
      status: 503,
      message: 'Actual mode is unavailable.',
    })
    const failed = workspaceReducer(pending, { type: 'analysis/failed', requestId: 2, error })
    expect(failed.analysis).toBe(before.analysis)
    expect(failed.selectedRouteId).toBe(before.selectedRouteId)
    expect(failed.isStale).toBe(true)
  })

  it('keeps displayed frame timestamp while a different hour is requested and ignores earlier completions', () => {
    const zero = {
      requestId: 2,
      analysisId: completeAnalysis.id,
      hour: 0,
      variable: 'wind' as const,
    }
    const requested = workspaceReducer(ready(), { type: 'frame/requested', request: zero })
    const displayed = workspaceReducer(requested, {
      type: 'frame/received',
      requestId: 2,
      frame: windFrame,
    })
    const next = workspaceReducer(displayed, {
      type: 'frame/requested',
      request: { ...zero, requestId: 3, hour: 1 },
    })
    expect(next.displayedFrame?.requested_at).toBe(windFrame.requested_at)
    expect(next.displayedFrame?.hour).toBe(0)
    expect(next.requestedFrame?.hour).toBe(1)
    expect(next.framePending).toBe(true)
    expect(workspaceReducer(next, { type: 'frame/received', requestId: 2, frame: windFrame })).toBe(
      next,
    )
  })

  it('never accepts a frame belonging to an earlier run', () => {
    const pending = workspaceReducer(ready(), { type: 'analysis/requested', requestId: 2 })
    const next = workspaceReducer(pending, {
      type: 'analysis/received',
      requestId: 2,
      analysis: noTravelAnalysis,
    })
    expect(workspaceReducer(next, { type: 'frame/received', requestId: 8, frame: windFrame })).toBe(
      next,
    )
    expect(next.displayedFrame).toBeNull()
    expect(next.analysis?.recommendation.route_id).toBeNull()
  })

  it('mode and frame selection do not mutate authoritative ranking/exposure', () => {
    const state = ready()
    const forecast = workspaceReducer(state, { type: 'mode/changed', mode: 'clock-forecast' })
    expect(forecast.analysis).toBe(state.analysis)
    expect(forecast.selectedRouteId).toBe(state.selectedRouteId)
    expect(forecast.analysis?.routes).toBe(state.analysis?.routes)
  })
})
