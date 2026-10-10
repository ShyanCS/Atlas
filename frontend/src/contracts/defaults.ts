import type { TripInput } from './types'

/** Explicit authored fallback draft, never a forecast or an analysis result. */
export const defaultTrip: TripInput = {
  mode: 'sample',
  scenario: 'complete',
  origin: { name: 'Chicago, IL', latitude: '41.8781', longitude: '-87.6298' },
  destination: { name: 'Atlanta, GA', latitude: '33.7490', longitude: '-84.3880' },
  departure_local: '2026-10-10T06:00:00',
  origin_timezone: 'America/Chicago',
  load_weight_lb: '24000',
  checkpoint_interval_miles: 25,
}
