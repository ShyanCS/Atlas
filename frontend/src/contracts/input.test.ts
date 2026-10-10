import { describe, expect, it } from 'vitest'
import { analysisToTripInput, createSampleInput } from './input'
import { completeAnalysis, scenariosFixture } from '../test/fixtures'

describe('request contract helpers', () => {
  it('creates explicit sample defaults without geocoding or timezone conversion', () => {
    const input = createSampleInput(scenariosFixture)
    expect(input.mode).toBe('sample')
    expect(input.origin).toBe(scenariosFixture.locations.origin)
    expect(input.departure_at).toBe(scenariosFixture.defaults.departure_at)
    expect(input.departure_local).toBe(scenariosFixture.defaults.departure_local)
    expect(input.departure_fold).toBe(scenariosFixture.defaults.departure_fold)
    expect(input.load_weight_lb).toBe('24000')
  })

  it('rejects a corrupt occurrence rather than inventing a DST choice', () => {
    const corrupt = structuredClone(scenariosFixture)
    corrupt.defaults.departure_fold = 2
    expect(() => createSampleInput(corrupt)).toThrow('unsupported departure occurrence')
  })
  it('restores required request fields and the backend-resolved local time without changing its instant', () => {
    const restored = analysisToTripInput(completeAnalysis)
    expect(restored.mode).toBe('sample')
    expect(restored.scenario).toBe(completeAnalysis.scenario)
    expect(restored.departure_at).toBe(completeAnalysis.inputs.departure_at)
    expect(restored.departure_local).toBe(completeAnalysis.inputs.departure_local)
    expect(restored.departure_fold).toBe(completeAnalysis.inputs.departure_fold)
  })
})
