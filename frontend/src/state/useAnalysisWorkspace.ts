import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import type { Scenarios, TripInput, WeatherVariable } from '../contracts/types'
import { atlasApi } from '../api/client'
import type { AnalysisApi } from '../api/client'
import { toApiError } from '../api/errors'
import { initialWorkspaceState, workspaceReducer } from './workspace'
import type { WorkspaceMode } from './workspace'

export function useAnalysisWorkspace(client: AnalysisApi = atlasApi) {
  const [state, dispatch] = useReducer(workspaceReducer, initialWorkspaceState)
  const [scenarios, setScenarios] = useState<Scenarios | null>(null)
  const [loadingScenarios, setLoadingScenarios] = useState(true)
  const [scenarioError, setScenarioError] = useState<ReturnType<typeof toApiError> | null>(null)
  const mounted = useRef(false)
  const sequence = useRef(0)
  const scenarioSequence = useRef(0)
  const scenarioController = useRef<AbortController | null>(null)
  const analysisController = useRef<AbortController | null>(null)
  const frameController = useRef<AbortController | null>(null)

  const reloadScenarios = useCallback(async () => {
    const requestId = ++scenarioSequence.current
    scenarioController.current?.abort()
    const controller = new AbortController()
    scenarioController.current = controller
    setLoadingScenarios(true)
    setScenarioError(null)
    try {
      const result = await client.getScenarios(controller.signal)
      if (mounted.current && requestId === scenarioSequence.current) setScenarios(result)
    } catch (error) {
      const apiError = toApiError(error)
      if (
        mounted.current &&
        requestId === scenarioSequence.current &&
        apiError.code !== 'REQUEST_ABORTED'
      )
        setScenarioError(apiError)
    } finally {
      if (mounted.current && requestId === scenarioSequence.current) setLoadingScenarios(false)
    }
  }, [client])

  useEffect(() => {
    mounted.current = true
    void reloadScenarios()
    return () => {
      mounted.current = false
      scenarioController.current?.abort()
      analysisController.current?.abort()
      frameController.current?.abort()
    }
  }, [reloadScenarios])

  const analyze = useCallback(
    async (input: TripInput) => {
      const requestId = ++sequence.current
      analysisController.current?.abort()
      frameController.current?.abort()
      const controller = new AbortController()
      analysisController.current = controller
      dispatch({ type: 'analysis/requested', requestId })
      try {
        const analysis = await client.createAnalysis(input, controller.signal)
        if (
          !mounted.current ||
          controller.signal.aborted ||
          analysisController.current !== controller
        )
          return null
        dispatch({ type: 'analysis/received', requestId, analysis })
        return analysis
      } catch (error) {
        const apiError = toApiError(error)
        if (mounted.current && apiError.code !== 'REQUEST_ABORTED')
          dispatch({ type: 'analysis/failed', requestId, error: apiError })
        return null
      }
    },
    [client],
  )

  const requestFrame = useCallback(
    async (hour: number, variable: WeatherVariable) => {
      const analysisId = state.analysis?.id
      if (!analysisId) return null
      const requestId = ++sequence.current
      frameController.current?.abort()
      const controller = new AbortController()
      frameController.current = controller
      dispatch({ type: 'frame/requested', request: { requestId, analysisId, hour, variable } })
      try {
        const frame = await client.getFrame(analysisId, hour, variable, controller.signal)
        if (!mounted.current || controller.signal.aborted || frameController.current !== controller)
          return null
        dispatch({ type: 'frame/received', requestId, frame })
        return frame
      } catch (error) {
        const apiError = toApiError(error)
        if (mounted.current && apiError.code !== 'REQUEST_ABORTED')
          dispatch({ type: 'frame/failed', requestId, analysisId, error: apiError })
        return null
      }
    },
    [client, state.analysis?.id],
  )

  const restore = useCallback(
    async (id: string) => {
      const requestId = ++sequence.current
      analysisController.current?.abort()
      frameController.current?.abort()
      const controller = new AbortController()
      analysisController.current = controller
      dispatch({ type: 'analysis/requested', requestId })
      try {
        const analysis = await client.getAnalysis(id, controller.signal)
        if (mounted.current && !controller.signal.aborted)
          dispatch({ type: 'analysis/received', requestId, analysis })
      } catch (error) {
        const apiError = toApiError(error)
        if (mounted.current && apiError.code !== 'REQUEST_ABORTED')
          dispatch({ type: 'analysis/failed', requestId, error: apiError })
      }
    },
    [client],
  )

  const selectRoute = useCallback(
    (routeId: string) => dispatch({ type: 'route/selected', routeId }),
    [],
  )
  const selectCheckpoint = useCallback(
    (routeId: string, checkpointId: string) =>
      dispatch({ type: 'checkpoint/selected', routeId, checkpointId }),
    [],
  )
  const setMode = useCallback((mode: WorkspaceMode) => dispatch({ type: 'mode/changed', mode }), [])
  const markStale = useCallback(() => dispatch({ type: 'draft/changed' }), [])
  const discardDraft = useCallback(() => dispatch({ type: 'draft/discarded' }), [])
  const clearError = useCallback(() => {
    dispatch({ type: 'error/cleared' })
    setScenarioError(null)
  }, [])

  return {
    state,
    scenarios,
    loadingScenarios,
    error: state.error ?? scenarioError,
    analysisPending: state.analysisRequestId !== null,
    framePending: state.framePending,
    analyze,
    restore,
    requestFrame,
    reloadScenarios,
    selectRoute,
    selectCheckpoint,
    setMode,
    markStale,
    discardDraft,
    clearError,
  }
}
