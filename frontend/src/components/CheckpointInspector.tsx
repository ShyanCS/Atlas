import type { Analysis, RouteCandidate, Checkpoint, Measurement } from '../contracts/types'
import { clock, number, riskLabels } from './format'
import { Icon, type IconName } from './Icon'
import { ExposureBreakdown } from './RouteCards'

function WeatherValue({
  label,
  caption,
  icon,
  measurement,
}: {
  label: string
  caption: string
  icon: IconName
  measurement: Measurement
}) {
  return (
    <div className="weather-value">
      <Icon name={icon} />
      <div>
        <strong>{label}</strong>
        <small>{caption}</small>
        {measurement.missing_reason && (
          <small className="missing-reason">
            {measurement.missing_reason.replaceAll('_', ' ')}
          </small>
        )}
      </div>
      <p>
        {number(measurement.value, label === 'Wind' ? 1 : 2)}
        <small>{measurement.unit}</small>
      </p>
    </div>
  )
}

export function CheckpointInspector({
  analysis,
  route,
  checkpoint,
  onCheckpoints,
  onSources,
}: {
  analysis: Analysis
  route: RouteCandidate
  checkpoint?: Checkpoint | undefined
  onCheckpoints: () => void
  onSources: () => void
}) {
  const preferred = analysis.routes.find(
    (candidate) => candidate.id === analysis.recommendation.route_id,
  )
  return (
    <aside
      className="inspector panel"
      aria-label="Recommendation and checkpoint inspector"
      id="inspector"
      tabIndex={-1}
    >
      <section
        className={`recommendation ${!preferred ? 'unverified' : ''}`}
        data-testid="recommendation"
      >
        <span className={`chip ${preferred ? 'preferred' : 'blocked'}`}>
          <Icon name={preferred ? 'check' : 'alert'} />
          {preferred
            ? analysis.sample_data
              ? 'Recommended'
              : 'Recommended route'
            : 'No verified recommendation'}
        </span>
        <h2>{preferred ? `Route ${preferred.code} preferred.` : 'Recommendation withheld.'}</h2>
        <p>
          {preferred
            ? 'Least Severe exposure, then High exposure, average risk and driving time.'
            : analysis.recommendation.reason}
        </p>
        <div className="decision-metrics">
          <div>
            <strong>
              {preferred ? number(preferred.exposure.severe_mi) : '—'}
              <small> mi</small>
            </strong>
            <span>Severe / preferred route</span>
          </div>
          <div>
            <strong>
              {preferred ? number(Number(preferred.verified_fraction) * 100, 0) : '—'}
              <small>%</small>
            </strong>
            <span>Required coverage</span>
          </div>
        </div>
      </section>
      <section className="checkpoint-inspection">
        <div className="panel-title">
          <span className="eyebrow">Route {route.code} / inspection</span>
          <button className="text-button" onClick={onCheckpoints}>
            {route.checkpoints.length} points
          </button>
        </div>
        {checkpoint ? (
          <>
            <h2>{checkpoint.label}</h2>
            <p className="checkpoint-mile">
              Mile {number(checkpoint.distance_mi)} · driving ETA{' '}
              {analysis.sample_data ? 'in Atlanta time' : `in ${analysis.inputs.origin_timezone}`}
            </p>
            <p className="checkpoint-time">
              {clock(
                checkpoint.eta_utc,
                analysis.sample_data ? 'America/New_York' : analysis.inputs.origin_timezone,
              )}
            </p>
            <p className={`risk-text risk-text-${checkpoint.overall_risk}`}>
              <Icon
                name={
                  checkpoint.overall_risk === 'no_travel'
                    ? 'stop'
                    : checkpoint.overall_risk === 'unknown'
                      ? 'info'
                      : 'wind'
                }
              />
              {riskLabels[checkpoint.overall_risk]}
              {!checkpoint.complete && ' · incomplete weather'}
            </p>
            <div className="weather-values">
              <WeatherValue
                label="Wind"
                caption="10 m wind speed"
                icon="wind"
                measurement={checkpoint.measurements.wind}
              />
              <WeatherValue
                label="Rain"
                caption="One-hour liquid depth"
                icon="rain"
                measurement={checkpoint.measurements.rain}
              />
              <WeatherValue
                label="Snow"
                caption={
                  analysis.sample_data
                    ? 'Hourly new-snow depth'
                    : 'Provider snowfall · 7:1 approximation'
                }
                icon="snow"
                measurement={checkpoint.measurements.snow}
              />
            </div>
            <div className={`explanation risk-explanation-${checkpoint.overall_risk}`}>
              <strong>Why this checkpoint is {riskLabels[checkpoint.overall_risk]}</strong>
              <p>{checkpoint.rule_explanations.at(-1)}</p>
              <details>
                <summary>Applied rules and exact values</summary>
                {checkpoint.rule_explanations.slice(0, -1).map((explanation, index) => (
                  <p key={index}>{explanation}</p>
                ))}
              </details>
              <p>
                Cargo: {number(analysis.inputs.load_weight_lb)} lb. Policy {analysis.policy_version}
                .
              </p>
            </div>
            <button className="text-button source-action" onClick={onSources}>
              Inspect source intervals and assumptions <Icon name="arrow" />
            </button>
          </>
        ) : (
          <div className="empty-inspection">
            <p>Select a checkpoint to inspect its ETA, weather and rule explanation.</p>
            <button className="btn" onClick={onCheckpoints}>
              Browse checkpoints
            </button>
          </div>
        )}
      </section>
    </aside>
  )
}

export function CheckpointTable({
  route,
  selectedId,
  onSelect,
}: {
  route: RouteCandidate
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="table-scroll">
      <table className="checkpoint-table">
        <caption>
          Route {route.code} · start, numbered interior checkpoints, and finish. Source times are
          available in the inspector.
        </caption>
        <thead>
          <tr>
            <th>Point</th>
            <th>Miles</th>
            <th>Arrival · UTC</th>
            <th>Risk</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((checkpoint) => (
            <tr key={checkpoint.id} className={checkpoint.id === selectedId ? 'chosen' : ''}>
              <th scope="row">{checkpoint.label}</th>
              <td>{number(checkpoint.distance_mi)}</td>
              <td>{clock(checkpoint.eta_utc, 'UTC')}</td>
              <td>
                <span className={`risk-text-${checkpoint.overall_risk}`}>
                  {riskLabels[checkpoint.overall_risk]}
                </span>
                {!checkpoint.complete && <small> · incomplete</small>}
              </td>
              <td>
                <button
                  className="btn"
                  onClick={() => onSelect(checkpoint.id)}
                  aria-label={`Inspect ${checkpoint.label} on Route ${route.code}`}
                >
                  Inspect
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SourceDetails({
  analysis,
  checkpoint,
  route,
}: {
  analysis: Analysis
  checkpoint?: Checkpoint | undefined
  route: RouteCandidate
}) {
  return (
    <div className="source-details">
      <p className="sample-disclosure">
        {analysis.sample_data
          ? 'The example trip uses illustrative route geometry and weather values. These measurements are not live forecasts.'
          : 'Open-Meteo / DWD ICON Global forecasts. Liquid rain combines rain + showers. Snowfall uses an approximate fixed 7:1 relationship. Current Free access is limited to personal noncommercial use. Model initialization is not exposed; native hourly model intervals are not verified.'}
      </p>
      <h3>Run and policy</h3>
      <p className="mono">{analysis.id}</p>
      <p>
        {analysis.policy_version} ·{' '}
        {analysis.sample_data ? 'Illustrative trip' : 'Provider forecasts'}
      </p>
      <p>
        Driving-time estimates exclude stops and duty breaks.{' '}
        {analysis.sample_data
          ? 'Routes are illustrated and do not establish truck-road legality.'
          : 'Provider truck sections and warnings determine routing eligibility, without a road-safety or dock-access guarantee.'}
      </p>
      {!analysis.sample_data && (
        <>
          <p>
            <a href="https://open-meteo.com/">Weather data by Open-Meteo</a> / DWD ·{' '}
            <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Values normalized
            to mph and inches/hour; provider snowfall is approximate.
          </p>
          <ul>
            {analysis.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Selected route exposure</h3>
      <ExposureBreakdown route={route} detailed />
      <p>
        Distance-weighted mean: {number(route.average_risk, 4)}. Unknown has no numeric ordinal. The
        denominator is classified distance. With incomplete coverage this is diagnostic only; it
        cannot make a route eligible.
      </p>
      {checkpoint &&
        Object.entries(checkpoint.measurements).map(([name, measurement]) => (
          <section className="provenance" key={name}>
            <h3>{name.charAt(0).toUpperCase() + name.slice(1)}</h3>
            <p>
              {measurement.value ?? 'Unknown'} {measurement.unit}
            </p>
            {measurement.missing_reason && <p>Missing: {measurement.missing_reason}</p>}
            <dl>
              {Object.entries(measurement.provenance ?? {}).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll('_', ' ')}</dt>
                  <dd>
                    {Array.isArray(value)
                      ? value.join(', ')
                      : typeof value === 'object'
                        ? JSON.stringify(value)
                        : String(value ?? '—')}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
    </div>
  )
}
