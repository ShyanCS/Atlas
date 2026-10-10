import type { RouteCandidate } from '../contracts/types'
import type { CSSProperties } from 'react'
import { clock, duration, number, riskLabels, routeColors } from './format'

const exposureKeys = ['low', 'moderate', 'high', 'severe', 'no_travel', 'unknown'] as const
export function ExposureBreakdown({
  route,
  detailed = false,
}: {
  route: RouteCandidate
  detailed?: boolean
}) {
  return (
    <div className="exposure-breakdown">
      <div className="exposure" aria-hidden="true">
        {exposureKeys.map((key) => (
          <i
            key={key}
            className={`risk-${key}`}
            style={{
              width: `${(100 * Number(route.exposure[`${key}_mi`])) / Number(route.distance_mi)}%`,
            }}
          />
        ))}
      </div>
      <span className="sr-only">
        {exposureKeys
          .map((key) => `${riskLabels[key]} ${number(route.exposure[`${key}_mi`])} miles`)
          .join('; ')}
      </span>
      {detailed && (
        <dl className="exposure-values">
          {exposureKeys.map((key) => (
            <div key={key}>
              <dt>
                <i className={`risk-dot risk-${key}`} />
                {riskLabels[key]}
              </dt>
              <dd>{number(route.exposure[`${key}_mi`])} mi</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

export function RouteCard({
  route,
  selected,
  preferred,
  onSelect,
}: {
  route: RouteCandidate
  selected: boolean
  preferred: boolean
  onSelect: () => void
}) {
  const noTravel = Number(route.exposure.no_travel_mi) > 0
  const status = noTravel
    ? 'No Travel'
    : !route.eligible
      ? 'Unverified'
      : preferred
        ? 'Preferred'
        : 'Alternative'
  return (
    <button
      className={`route-card ${selected ? 'selected' : ''}`}
      style={{ '--route-color': routeColors[route.code] } as CSSProperties}
      aria-pressed={selected}
      aria-label={`Inspect Route ${route.code}, ${status}`}
      onClick={onSelect}
      data-testid={`route-${route.code}`}
    >
      <div className="card-top">
        <span className="route-id">{route.code}</span>
        <div className="card-title">
          <h3>Route {route.code}</h3>
          <p>{route.label}</p>
        </div>
        <span className={`chip ${noTravel ? 'blocked' : preferred ? 'preferred' : ''}`}>
          {status}
        </span>
      </div>
      <div className="card-stats">
        {duration(route.duration_seconds)}
        <span>/</span>
        {number(route.distance_mi, 0)}
        <small> mi</small>
      </div>
      <ExposureBreakdown route={route} />
      <div className="risk-stats">
        <span>
          Severe <b>{number(route.exposure.severe_mi)} mi</b>
        </span>
        <span>
          {noTravel ? 'No Travel' : !route.eligible ? 'Unknown' : 'High'}{' '}
          <b>
            {number(
              noTravel
                ? route.exposure.no_travel_mi
                : !route.eligible
                  ? route.exposure.unknown_mi
                  : route.exposure.high_mi,
            )}{' '}
            mi
          </b>
        </span>
      </div>
      <div className="card-arrival">
        Arrival{' '}
        <b>
          {clock(
            route.arrival_at,
            route.routing_eligibility_basis === 'authored_sample_assumption'
              ? 'America/New_York'
              : 'UTC',
          )}
        </b>
        <span>{number(Number(route.verified_fraction) * 100, 0)}% required coverage</span>
      </div>
    </button>
  )
}
