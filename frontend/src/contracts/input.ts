import type { Analysis, Scenarios, TripInput } from './types'

function interval(value: number): 10 | 25 | 50 {
  if (value === 10 || value === 25 || value === 50) return value
  throw new Error('The API returned an unsupported checkpoint interval.')
}

function occurrence(value: number | null): 0 | 1 | null {
  if (value === null || value === 0 || value === 1) return value
  throw new Error('The API returned an unsupported departure occurrence.')
}

export function createSampleInput(scenarios: Scenarios): TripInput {
  return {
    mode: 'sample',
    scenario: 'complete',
    origin: scenarios.locations.origin,
    destination: scenarios.locations.destination,
    departure_at: scenarios.defaults.departure_at,
    departure_local: scenarios.defaults.departure_local,
    departure_fold: occurrence(scenarios.defaults.departure_fold),
    origin_timezone: scenarios.defaults.origin_timezone,
    load_weight_lb: scenarios.defaults.load_weight_lb,
    checkpoint_interval_miles: interval(scenarios.defaults.checkpoint_interval_miles),
  }
}

/** Restore the submitted context, without deriving a timezone or changing the instant. */
export function analysisToTripInput(analysis: Analysis): TripInput {
  const input = analysis.inputs
  const fold = occurrence(input.departure_fold)
  return {
    mode: analysis.mode,
    scenario: analysis.scenario,
    origin: input.origin,
    destination: input.destination,
    departure_at: input.departure_at,
    origin_timezone: input.origin_timezone,
    load_weight_lb: input.load_weight_lb,
    checkpoint_interval_miles: interval(input.checkpoint_interval_miles),
    ...(input.departure_local !== null ? { departure_local: input.departure_local } : {}),
    departure_fold: fold,
    ...(input.truck_profile ? { truck_profile: input.truck_profile } : {}),
  }
}
