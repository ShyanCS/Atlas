import type { Analysis, WeatherFrame, WeatherVariable } from '../contracts/types'
import type { ApiError } from '../api/errors'

export type WorkspaceMode = 'arrival-risk' | 'clock-forecast'
export interface FrameRequest {
  requestId: number
  analysisId: string
  hour: number
  variable: WeatherVariable
}
export interface WorkspaceState {
  analysis: Analysis | null
  selectedRouteId: string | null
  selectedCheckpointId: string | null
  mode: WorkspaceMode
  requestedFrame: FrameRequest | null
  displayedFrame: WeatherFrame | null
  framePending: boolean
  analysisRequestId: number | null
  draftRevision: number
  analysisRequestRevision: number
  isStale: boolean
  error: ApiError | null
}

export const initialWorkspaceState: WorkspaceState = {
  analysis: null,
  selectedRouteId: null,
  selectedCheckpointId: null,
  mode: 'arrival-risk',
  requestedFrame: null,
  displayedFrame: null,
  framePending: false,
  analysisRequestId: null,
  draftRevision: 0,
  analysisRequestRevision: 0,
  isStale: false,
  error: null,
}

export type WorkspaceAction =
  | { type: 'analysis/requested'; requestId: number }
  | { type: 'analysis/received'; requestId: number; analysis: Analysis }
  | { type: 'analysis/failed'; requestId: number; error: ApiError }
  | { type: 'draft/changed' }
  | { type: 'draft/discarded' }
  | { type: 'route/selected'; routeId: string }
  | { type: 'checkpoint/selected'; routeId: string; checkpointId: string }
  | { type: 'mode/changed'; mode: WorkspaceMode }
  | { type: 'frame/requested'; request: FrameRequest }
  | { type: 'frame/received'; requestId: number; frame: WeatherFrame }
  | { type: 'frame/failed'; requestId: number; analysisId: string; error: ApiError }
  | { type: 'error/cleared' }

export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.type) {
    case 'analysis/requested':
      return {
        ...state,
        analysisRequestId: action.requestId,
        analysisRequestRevision: state.draftRevision,
        isStale: state.analysis !== null,
        framePending: false,
        requestedFrame: null,
        error: null,
      }
    case 'analysis/received': {
      if (state.analysisRequestId !== action.requestId) return state
      const preferred = action.analysis.routes.find(
        (route) => route.id === action.analysis.recommendation.route_id,
      )
      return {
        ...state,
        analysis: action.analysis,
        analysisRequestId: null,
        selectedRouteId: preferred?.id ?? action.analysis.routes[0]?.id ?? null,
        selectedCheckpointId: null,
        requestedFrame: null,
        displayedFrame: null,
        framePending: false,
        isStale: state.analysisRequestRevision !== state.draftRevision,
        error: null,
      }
    }
    case 'analysis/failed':
      return state.analysisRequestId === action.requestId
        ? {
            ...state,
            analysisRequestId: null,
            isStale: state.analysis !== null,
            error: action.error,
          }
        : state
    case 'draft/changed':
      return {
        ...state,
        draftRevision: state.draftRevision + 1,
        isStale: state.analysis !== null || state.analysisRequestId !== null,
      }
    case 'draft/discarded':
      if (state.analysisRequestId !== null) return state
      return { ...state, draftRevision: state.draftRevision + 1, isStale: false }
    case 'route/selected':
      if (!state.analysis?.routes.some((route) => route.id === action.routeId)) return state
      return {
        ...state,
        selectedRouteId: action.routeId,
        selectedCheckpointId:
          state.selectedRouteId === action.routeId ? state.selectedCheckpointId : null,
      }
    case 'checkpoint/selected':
      if (
        !state.analysis?.routes
          .find((route) => route.id === action.routeId)
          ?.checkpoints.some(
            (point) => point.id === action.checkpointId && point.route_id === action.routeId,
          )
      )
        return state
      return {
        ...state,
        selectedRouteId: action.routeId,
        selectedCheckpointId: action.checkpointId,
      }
    case 'mode/changed':
      return { ...state, mode: action.mode }
    case 'frame/requested':
      if (state.analysis?.id !== action.request.analysisId) return state
      return { ...state, requestedFrame: action.request, framePending: true, error: null }
    case 'frame/received':
      if (
        state.analysis?.id !== action.frame.analysis_id ||
        state.requestedFrame?.requestId !== action.requestId ||
        state.requestedFrame.hour !== action.frame.hour ||
        state.requestedFrame.variable !== action.frame.variable
      )
        return state
      return { ...state, displayedFrame: action.frame, framePending: false, error: null }
    case 'frame/failed':
      return state.analysis?.id === action.analysisId &&
        state.requestedFrame?.requestId === action.requestId
        ? { ...state, framePending: false, error: action.error }
        : state
    case 'error/cleared':
      return { ...state, error: null }
  }
}
