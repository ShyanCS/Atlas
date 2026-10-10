import type { Analysis, WeatherFrame } from '../contracts/types'
import type { MapMode } from './OperationalMap'
import { datedClock } from './format'
import { Icon } from './Icon'

export type Variable = 'wind' | 'rain' | 'snow'
export function ForecastTimeline({
  analysis,
  frame,
  hour,
  variable,
  pending,
  mode,
  onRequest,
  onMode,
}: {
  analysis: Analysis
  frame: WeatherFrame | null
  hour: number
  variable: Variable
  pending: boolean
  mode: MapMode
  onRequest: (hour: number, variable: Variable) => void
  onMode: (mode: MapMode) => void
}) {
  const requestedClock = new Date(
    new Date(analysis.inputs.departure_at).getTime() + hour * 3_600_000,
  ).toISOString()
  return (
    <section
      className="timeline panel"
      id="forecast"
      aria-labelledby="forecast-title"
      tabIndex={-1}
    >
      <div className="timeline-title">
        <h2 id="forecast-title">
          Forecast viewer <span>/ 0–48 hours</span>
        </h2>
        <span className="frame-clock">
          {datedClock(requestedClock, analysis.inputs.origin_timezone)} · +{hour}h
        </span>
      </div>
      <div className="timeline-controls">
        <button
          className="btn icon-only"
          aria-label="Previous forecast hour"
          disabled={hour === 0}
          onClick={() => {
            onMode('clock-forecast')
            onRequest(hour - 1, variable)
          }}
        >
          −
        </button>
        <label className="sr-only" htmlFor="forecast-hour">
          Requested forecast hour offset
        </label>
        <input
          id="forecast-hour"
          type="range"
          min="0"
          max="48"
          step="1"
          value={hour}
          aria-valuetext={`Plus ${hour} hours, ${datedClock(requestedClock, analysis.inputs.origin_timezone)}`}
          onChange={(event) => {
            onMode('clock-forecast')
            onRequest(Number(event.target.value), variable)
          }}
        />
        <button
          className="btn icon-only"
          aria-label="Next forecast hour"
          disabled={hour === 48}
          onClick={() => {
            onMode('clock-forecast')
            onRequest(hour + 1, variable)
          }}
        >
          +
        </button>
      </div>
      <div className="timeline-ticks" aria-hidden="true">
        <span>+0h</span>
        <span>+12h</span>
        <span>+24h</span>
        <span>+36h</span>
        <span>+48h</span>
      </div>
      <div className="timeline-footer">
        <div className="field-tabs" role="group" aria-label="Raw weather variable">
          {(['wind', 'rain', 'snow'] as const).map((field) => (
            <button
              className={variable === field ? 'active' : ''}
              aria-pressed={variable === field}
              key={field}
              onClick={() => {
                onMode('clock-forecast')
                onRequest(hour, field)
              }}
            >
              <Icon name={field} />
              {field.charAt(0).toUpperCase() + field.slice(1)}
            </button>
          ))}
        </div>
        <span className="frame-status" role="status">
          {pending
            ? 'Loading forecast frame…'
            : frame
              ? `${frame.coverage.known_cells}/${frame.coverage.total_cells} forecast locations · ${frame.acquisition_status}`
              : 'Choose a forecast hour'}
        </span>
      </div>
      {frame && (
        <p className={frame.coverage.status !== 'complete' ? 'coverage-warning' : 'timeline-note'}>
          {frame.coverage.status !== 'complete' ? 'Unknown cells stay unclassified. ' : ''}
          Displayed: +{frame.hour}h {frame.variable} ·{' '}
          {datedClock(frame.requested_at, analysis.inputs.origin_timezone)}.{' '}
          {pending && 'The displayed frame keeps its timestamp while the next frame loads.'}
        </p>
      )}
      <p className="timeline-note">
        {mode === 'arrival-risk'
          ? 'Arrival colors use each checkpoint’s own ETA.'
          : 'Raw-variable colors describe one clock time.'}{' '}
        Scrubbing never changes the saved recommendation.
      </p>
    </section>
  )
}
