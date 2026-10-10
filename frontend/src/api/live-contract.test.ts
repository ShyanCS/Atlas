import { describe, expect, it } from 'vitest'
import { completeAnalysis, windFrame } from '../test/fixtures'
import { isAnalysis, isWeatherFrame } from './validation'
import { analysisToTripInput } from '../contracts/input'

/** Authored contract variants. These are never displayed as real provider results. */
function authoredLive() {
  const value = structuredClone(completeAnalysis)
  value.mode = 'live'
  value.sample_data = false
  for (const route of value.routes) {
    route.routing_eligibility_basis = 'provider_truck_sections_and_notices'
    for (const point of route.checkpoints)
      for (const measurement of Object.values(point.measurements)) {
        measurement.provenance.kind = 'forecast'
        measurement.provenance.model_run_at = null
        measurement.provenance.native_interval_seconds = null
      }
  }
  return value
}

describe('live assessment transport contract', () => {
  it('accepts explicit live mode with nullable model run without frontend re-ranking', () => {
    const analysis = authoredLive()
    expect(isAnalysis(analysis)).toBe(true)
    expect(analysisToTripInput(analysis).mode).toBe('live')
    expect(analysis.recommendation.route_id).toBe(completeAnalysis.recommendation.route_id)
  })

  it('rejects mislabeled sample measurements inside a live analysis', () => {
    const analysis = authoredLive()
    analysis.routes[0]!.checkpoints[0]!.measurements.snow.provenance.kind = 'synthetic'
    expect(isAnalysis(analysis)).toBe(false)
    expect(isAnalysis({ ...analysis, sample_data: true })).toBe(false)
  })

  it('accepts actual frame provenance and rejects a mode mismatch', () => {
    const frame = structuredClone(windFrame)
    frame.mode = 'live'
    frame.sample_data = false
    for (const cell of frame.cells) {
      cell.measurement.provenance.kind = 'forecast'
      cell.measurement.provenance.model_run_at = null
    }
    expect(isWeatherFrame(frame)).toBe(true)
    expect(isWeatherFrame({ ...frame, sample_data: true })).toBe(false)
  })
})
