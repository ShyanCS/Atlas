import type { Analysis, Scenarios, WeatherFrame } from '../contracts/types'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
const text = (value: unknown): value is string => typeof value === 'string'
const decimal = (value: unknown) =>
  text(value) &&
  /^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) &&
  Number.isFinite(Number(value))
const integer = (value: unknown) =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0
const instant = (value: unknown) => text(value) && Number.isFinite(Date.parse(value))
const strings = (value: unknown) => Array.isArray(value) && value.every(text)
const risk = (value: unknown) =>
  text(value) && ['low', 'moderate', 'high', 'severe', 'no_travel', 'unknown'].includes(value)
const sample = (value: Record<string, unknown>) =>
  value.mode === 'sample' && value.sample_data === true
const analysisMode = (value: Record<string, unknown>) =>
  sample(value) || (value.mode === 'live' && value.sample_data === false)
const position = (value: unknown) =>
  Array.isArray(value) &&
  value.length === 2 &&
  value.every((part) => typeof part === 'number' && Number.isFinite(part))
const line = (value: unknown) =>
  isRecord(value) &&
  value.type === 'LineString' &&
  Array.isArray(value.coordinates) &&
  value.coordinates.length >= 2 &&
  value.coordinates.every(position)
const polygon = (value: unknown) =>
  isRecord(value) &&
  value.type === 'Polygon' &&
  Array.isArray(value.coordinates) &&
  value.coordinates.length > 0 &&
  value.coordinates.every((ring) => Array.isArray(ring) && ring.length >= 4 && ring.every(position))
const coordinate = (value: unknown) =>
  isRecord(value) && decimal(value.latitude) && decimal(value.longitude)
const location = (value: unknown) => coordinate(value) && isRecord(value) && text(value.name)
const nullableInstant = (value: unknown) => value === null || instant(value)

const provenance = (value: unknown) =>
  isRecord(value) &&
  (value.kind === 'synthetic' || value.kind === 'forecast') &&
  text(value.source) &&
  text(value.model) &&
  (value.kind === 'synthetic'
    ? instant(value.model_run_at)
    : nullableInstant(value.model_run_at)) &&
  nullableInstant(value.valid_at) &&
  instant(value.retrieved_at) &&
  nullableInstant(value.interval_start) &&
  nullableInstant(value.interval_end) &&
  (value.native_interval_seconds === null || integer(value.native_interval_seconds)) &&
  strings(value.quality_flags)

const measurement = (value: unknown) =>
  isRecord(value) &&
  (value.value === null || decimal(value.value)) &&
  (value.unit === 'mph' || value.unit === 'in/hour') &&
  (value.missing_reason === null || text(value.missing_reason)) &&
  provenance(value.provenance)

const checkpoint = (value: unknown, routeId: string) =>
  isRecord(value) &&
  text(value.id) &&
  value.route_id === routeId &&
  integer(value.index) &&
  text(value.label) &&
  decimal(value.distance_mi) &&
  instant(value.eta_utc) &&
  coordinate(value.coordinate) &&
  risk(value.overall_risk) &&
  (value.known_lower_bound === null || risk(value.known_lower_bound)) &&
  typeof value.complete === 'boolean' &&
  strings(value.governing_conditions) &&
  strings(value.rule_ids) &&
  text(value.timing_quality) &&
  strings(value.rule_explanations) &&
  decimal(value.anchor_gap_mi) &&
  decimal(value.anchor_gap_seconds) &&
  isRecord(value.measurements) &&
  measurement(value.measurements.wind) &&
  measurement(value.measurements.rain) &&
  measurement(value.measurements.snow)

const route = (value: unknown) =>
  isRecord(value) &&
  text(value.id) &&
  text(value.code) &&
  text(value.label) &&
  line(value.geometry) &&
  decimal(value.distance_mi) &&
  integer(value.duration_seconds) &&
  instant(value.departure_at) &&
  instant(value.arrival_at) &&
  text(value.timing_quality) &&
  ['authored_sample_assumption', 'provider_truck_sections_and_notices'].includes(
    String(value.routing_eligibility_basis),
  ) &&
  isRecord(value.exposure) &&
  ['low_mi', 'moderate_mi', 'high_mi', 'severe_mi', 'no_travel_mi', 'unknown_mi'].every((key) =>
    decimal((value.exposure as Record<string, unknown>)[key]),
  ) &&
  (value.average_risk === null || decimal(value.average_risk)) &&
  decimal(value.verified_fraction) &&
  typeof value.eligible === 'boolean' &&
  strings(value.eligibility_reasons) &&
  strings(value.route_notices) &&
  (value.rank === null || integer(value.rank)) &&
  Array.isArray(value.checkpoints) &&
  value.checkpoints.every((point) => checkpoint(point, value.id as string)) &&
  Array.isArray(value.risk_spans) &&
  value.risk_spans.every(
    (span) =>
      isRecord(span) &&
      decimal(span.start_mi) &&
      decimal(span.end_mi) &&
      risk(span.classification) &&
      line(span.geometry) &&
      strings(span.checkpoint_ids) &&
      strings(span.governing_conditions),
  )

/** Check transport structure, identities and units; never compute risk or exposure here. */
export function isAnalysis(value: unknown): value is Analysis {
  if (
    !isRecord(value) ||
    !analysisMode(value) ||
    !text(value.id) ||
    value.status !== 'complete' ||
    !text(value.policy_version) ||
    !text(value.fixture_version) ||
    !['complete', 'partial', 'no-travel'].includes(String(value.scenario)) ||
    ![value.created_at, value.started_at, value.completed_at, value.expires_at].every(instant) ||
    !Array.isArray(value.lifecycle) ||
    !value.lifecycle.every((item) => isRecord(item) && text(item.status) && instant(item.at)) ||
    !isRecord(value.inputs) ||
    !location(value.inputs.origin) ||
    !location(value.inputs.destination) ||
    !instant(value.inputs.departure_at) ||
    !text(value.inputs.origin_timezone) ||
    !(value.inputs.departure_local === null || text(value.inputs.departure_local)) ||
    ![null, 0, 1].includes(value.inputs.departure_fold as number | null) ||
    !decimal(value.inputs.load_weight_lb) ||
    ![10, 25, 50].includes(Number(value.inputs.checkpoint_interval_miles)) ||
    !Array.isArray(value.routes) ||
    !value.routes.every(route) ||
    !strings(value.warnings) ||
    !isRecord(value.recommendation) ||
    !['recommended', 'blocked', 'unverified'].includes(String(value.recommendation.state)) ||
    !(value.recommendation.route_id === null || text(value.recommendation.route_id)) ||
    !text(value.recommendation.reason) ||
    !strings(value.recommendation.ranking_criteria)
  )
    return false
  const ids = value.routes.map((candidate) => (candidate as Record<string, unknown>).id)
  for (const candidate of value.routes) {
    const r = candidate as Record<string, unknown>
    if (
      r.routing_eligibility_basis !==
      (value.mode === 'sample'
        ? 'authored_sample_assumption'
        : 'provider_truck_sections_and_notices')
    )
      return false
    for (const point of r.checkpoints as Record<string, unknown>[]) {
      for (const m of Object.values(
        point.measurements as Record<string, Record<string, unknown>>,
      )) {
        if (
          (m.provenance as Record<string, unknown>).kind !==
          (value.mode === 'sample' ? 'synthetic' : 'forecast')
        )
          return false
      }
    }
  }
  if (new Set(ids).size !== ids.length) return false
  if (value.recommendation.route_id !== null) {
    const preferred = value.routes.find(
      (candidate) =>
        isRecord(candidate) &&
        candidate.id === (value.recommendation as Record<string, unknown>).route_id,
    )
    if (
      !isRecord(preferred) ||
      preferred.eligible !== true ||
      value.recommendation.state !== 'recommended'
    )
      return false
  } else if (value.recommendation.state === 'recommended') return false
  return true
}

export function isScenarios(value: unknown): value is Scenarios {
  return (
    isRecord(value) &&
    sample(value) &&
    isRecord(value.locations) &&
    location(value.locations.origin) &&
    location(value.locations.destination) &&
    isRecord(value.defaults) &&
    instant(value.defaults.departure_at) &&
    text(value.defaults.origin_timezone) &&
    text(value.defaults.departure_local) &&
    [null, 0, 1].includes(value.defaults.departure_fold as number | null) &&
    decimal(value.defaults.load_weight_lb) &&
    [10, 25, 50].includes(Number(value.defaults.checkpoint_interval_miles)) &&
    Array.isArray(value.scenarios) &&
    value.scenarios.length > 0 &&
    value.scenarios.every(
      (item) =>
        isRecord(item) &&
        ['complete', 'partial', 'no-travel'].includes(String(item.id)) &&
        text(item.label) &&
        text(item.description),
    )
  )
}

export function isWeatherFrame(value: unknown): value is WeatherFrame {
  return (
    isRecord(value) &&
    analysisMode(value) &&
    text(value.analysis_id) &&
    integer(value.hour) &&
    Number(value.hour) <= 48 &&
    ['wind', 'rain', 'snow'].includes(String(value.variable)) &&
    instant(value.requested_at) &&
    text(value.unit) &&
    value.classification_basis === 'selected_variable' &&
    ['ready', 'partial', 'missing'].includes(String(value.acquisition_status)) &&
    isRecord(value.coverage) &&
    ['complete', 'partial', 'missing'].includes(String(value.coverage.status)) &&
    integer(value.coverage.known_cells) &&
    integer(value.coverage.total_cells) &&
    Number(value.coverage.known_cells) <= Number(value.coverage.total_cells) &&
    strings(value.coverage.reason_codes) &&
    strings(value.warnings) &&
    Array.isArray(value.cells) &&
    value.cells.every(
      (cell) =>
        isRecord(cell) &&
        text(cell.id) &&
        polygon(cell.geometry) &&
        coordinate(cell.coordinate) &&
        measurement(cell.measurement) &&
        isRecord(cell.measurement) &&
        isRecord(cell.measurement.provenance) &&
        cell.measurement.provenance.kind === (value.mode === 'sample' ? 'synthetic' : 'forecast'),
    )
  )
}
