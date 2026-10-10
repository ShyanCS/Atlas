import { useEffect, useRef, useState } from 'react'
import { useAnalysisWorkspace } from './state/useAnalysisWorkspace'
import { analysisToTripInput, createSampleInput } from './contracts/input'
import { defaultTrip } from './contracts/defaults'
import { AtlasBrand, Icon } from './components/Icon'
import { TripForm } from './components/TripForm'
import { RouteCard, ExposureBreakdown } from './components/RouteCards'
import {
  CheckpointInspector,
  CheckpointTable,
  SourceDetails,
} from './components/CheckpointInspector'
import { ForecastTimeline } from './components/ForecastTimeline'
import { OperationalMap } from './components/OperationalMap'
import { AnalysisStatus } from './components/AnalysisStatus'
import { Dialog } from './components/Dialog'
import { datedClock, number, duration, riskLabels } from './components/format'

type DialogKind = 'trip' | 'compare' | 'checkpoints' | 'sources' | 'summary' | null
const dialogTitles = {
  trip: 'Plan a trip',
  compare: 'Compare evaluated routes',
  checkpoints: 'Checkpoint weather at arrival',
  sources: 'Sources, intervals and exposure',
  summary: 'Sample driver summary',
}

export default function App() {
  const workspace = useAnalysisWorkspace()
  const { restore } = workspace
  const { state, analyze, selectRoute, selectCheckpoint, requestFrame, setMode, markStale } =
    workspace
  const [dialog, setDialog] = useState<DialogKind>(null)
  const initialized = useRef<string | null>(null)
  const analysis = state.analysis
  const live = analysis?.mode === 'live'
  const selected = analysis?.routes.find((route) => route.id === state.selectedRouteId)
  const checkpoint = selected?.checkpoints.find((point) => point.id === state.selectedCheckpointId)
  const preferred = analysis?.routes.find((route) => route.id === analysis.recommendation.route_id)
  const hour = state.requestedFrame?.hour ?? 0
  const variable = state.requestedFrame?.variable ?? 'wind'
  const sampleDraft = workspace.scenarios ? createSampleInput(workspace.scenarios) : defaultTrip
  const openTrip = () => {
    workspace.clearError()
    setDialog('trip')
  }
  const closeDialog = () => {
    if (dialog === 'trip') workspace.discardDraft()
    setDialog(null)
  }
  const scrollWorkspaceTo = (id: string) => {
    const main = document.getElementById('main')
    const target = document.getElementById(id)
    if (!main || !target) return
    const top =
      id === 'main'
        ? 0
        : main.scrollTop +
          target.getBoundingClientRect().top -
          main.getBoundingClientRect().top -
          16
    main.scrollTo({ top, behavior: 'instant' })
    target.focus({ preventScroll: true })
  }

  useEffect(() => {
    const saved = new URLSearchParams(window.location.search).get('analysis')
    if (saved) void restore(saved)
  }, [restore])

  useEffect(() => {
    if (!analysis || initialized.current === analysis.id) return
    initialized.current = analysis.id
    const candidate =
      analysis.routes.find((route) => route.id === analysis.recommendation.route_id) ??
      analysis.routes[0]
    const point =
      candidate?.checkpoints.find(
        (item) =>
          item.overall_risk === 'high' ||
          item.overall_risk === 'severe' ||
          item.overall_risk === 'no_travel',
      ) ??
      candidate?.checkpoints.find((item) => item.overall_risk === 'moderate') ??
      candidate?.checkpoints[0]
    if (candidate && point) selectCheckpoint(candidate.id, point.id)
    void requestFrame(0, 'wind')
  }, [analysis, requestFrame, selectCheckpoint])

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to dispatch workspace
      </a>
      <header className="topbar">
        <div className="top-left">
          <AtlasBrand />
          <nav className="nav" aria-label="Application">
            <a href="#main" className="active" aria-current="page">
              Dispatch
            </a>
            <span title="Later milestone">
              Trip Intelligence <small>Later</small>
            </span>
            <span title="Later milestone">
              Departure Lab <small>Later</small>
            </span>
          </nav>
        </div>
        <div className="top-right">
          <span className="sample">{live ? 'LIVE FORECAST · ASSESSMENT' : 'SAMPLE DATA'}</span>
          <span className="mono quiet desktop-only">ASSESSMENT EVALUATION</span>
        </div>
      </header>
      <main id="main" className="workspace" tabIndex={-1}>
        <div className="workspace-head">
          <div>
            <p className="crumb mono">
              DISPATCH /{' '}
              {analysis ? `RUN ${analysis.id.slice(0, 8).toUpperCase()}` : 'SAMPLE WORKSPACE'}
            </p>
            <h1>
              {analysis
                ? `${analysis.inputs.origin.name} → ${analysis.inputs.destination.name}`
                : 'Chicago → Atlanta'}
            </h1>
          </div>
          <div className="workspace-meta">
            <div className="snapshot desktop-only">
              <strong>
                {analysis
                  ? `${live ? 'Live' : 'Sample'} analysis · ${datedClock(analysis.completed_at ?? analysis.created_at)}`
                  : 'Create a sample analysis'}
              </strong>
              <span>
                {analysis
                  ? `${analysis.policy_version} · ${state.isStale ? 'previous inputs' : 'immutable result'}`
                  : 'No live routing or forecast data'}
              </span>
            </div>
            <button
              className="btn desktop-only"
              disabled={!analysis}
              onClick={() => setDialog('summary')}
            >
              <Icon name="truck" />
              Driver summary
            </button>
            <button
              className="btn mobile-route-button"
              disabled={!analysis}
              onClick={() => setDialog('compare')}
            >
              {analysis?.routes.length ?? 0} routes
            </button>
            <button className="btn ghost desktop-only" onClick={openTrip}>
              New trip <Icon name="arrow" />
            </button>
          </div>
        </div>
        <p className="global-disclosure">
          {live
            ? 'Personal noncommercial assessment. Live truck routes and forecast weather; snowfall uses a disclosed fixed 7:1 provider approximation. Not for operational travel decisions.'
            : 'Hypothetical weather and independently illustrated routes. Not for travel decisions.'}
        </p>
        <AnalysisStatus
          pending={workspace.analysisPending}
          error={workspace.error?.message}
          stale={state.isStale}
          noRecommendation={!!analysis && !analysis.recommendation.route_id}
          onRetry={openTrip}
        />
        <div className={`canvas-layout ${analysis ? '' : 'no-analysis'}`}>
          <div className="rail">
            <section className="panel trip-mini" aria-label="Submitted trip parameters">
              <div className="panel-title">
                <h2>Your trip</h2>
                <button
                  className="text-button desktop-only"
                  aria-label="Edit sample trip"
                  onClick={openTrip}
                >
                  <Icon name="edit" />
                </button>
              </div>
              <div className="stop-field desktop-only">
                <Icon name="pin" />
                <span>Origin</span>
                <strong>{analysis?.inputs.origin.name ?? 'Chicago, Illinois'}</strong>
              </div>
              <div className="stop-field desktop-only">
                <Icon name="pin" />
                <span>Destination</span>
                <strong>{analysis?.inputs.destination.name ?? 'Atlanta, Georgia'}</strong>
              </div>
              <div className="mini-inputs">
                <div>
                  <span>Departure · {analysis?.inputs.origin_timezone ?? 'Chicago'}</span>
                  <strong>
                    {analysis
                      ? datedClock(analysis.inputs.departure_at, analysis.inputs.origin_timezone)
                      : 'Oct 10 · 06:00 CDT'}
                  </strong>
                </div>
                <div>
                  <span>Cargo load</span>
                  <strong>
                    {number(analysis?.inputs.load_weight_lb ?? defaultTrip.load_weight_lb)} lb
                  </strong>
                </div>
              </div>
              <div className="trip-actions">
                <button className="btn primary" onClick={openTrip}>
                  <Icon name="refresh" />
                  {analysis ? 'Edit & analyze' : 'Plan sample trip'}
                </button>
                <button className="btn" onClick={() => setDialog('sources')} disabled={!analysis}>
                  <Icon name="info" />
                  Assumptions
                </button>
              </div>
            </section>
            <div className="rail-heading desktop-only">
              <span className="eyebrow">Route comparison</span>
              <span>
                {analysis?.routes.length ?? 0} {live ? 'truck candidates' : 'sample options'}
              </span>
            </div>
            <section className="route-list" aria-label="Evaluated sample route candidates">
              {analysis?.routes
                .slice()
                .sort((a, b) => (a.rank ?? 100) - (b.rank ?? 100))
                .map((route) => (
                  <RouteCard
                    key={route.id}
                    route={route}
                    selected={route.id === state.selectedRouteId}
                    preferred={route.id === analysis.recommendation.route_id}
                    onSelect={() => selectRoute(route.id)}
                  />
                ))}
            </section>
            {!analysis && (
              <section className="panel empty-card">
                <Icon name="compass" />
                <h2>Plan. Understand. Dispatch.</h2>
                <p>Compare three illustrated candidates under the disclosed weather-risk policy.</p>
                <button
                  className="btn primary wide"
                  onClick={() => {
                    void analyze(sampleDraft)
                  }}
                  disabled={workspace.analysisPending}
                >
                  {workspace.analysisPending ? 'Analyzing sample…' : 'Analyze default sample'}
                </button>
              </section>
            )}
            <p className="rail-note">
              <Icon name="info" />
              Driving-time estimates exclude stops and duty breaks.{' '}
              {live
                ? 'Provider truck compatibility is not a road-safety guarantee.'
                : 'Sample routes do not establish road legality.'}
            </p>
            <section className="ranking-rule panel">
              <strong>Assessment ranking, in order</strong>
              <p>Severe mi → High mi → mean → time</p>
              <span>Eligibility first · no weighted AI score</span>
            </section>
          </div>
          <div className="map-column">
            <OperationalMap
              analysis={analysis}
              selectedRouteId={state.selectedRouteId}
              checkpoint={checkpoint}
              mode={state.mode}
              frame={state.displayedFrame}
              framePending={workspace.framePending}
              onMode={setMode}
              onRoute={selectRoute}
              onCheckpoint={selectCheckpoint}
              onCheckpointList={() => setDialog('checkpoints')}
            />
            {analysis ? (
              <ForecastTimeline
                analysis={analysis}
                frame={state.displayedFrame}
                hour={hour}
                variable={variable}
                pending={workspace.framePending}
                mode={state.mode}
                onRequest={(h, v) => {
                  void requestFrame(h, v)
                }}
                onMode={setMode}
              />
            ) : (
              <section className="panel empty-timeline">
                <h2>
                  Forecast viewer <span>/ 0–48 hours</span>
                </h2>
                <p>
                  Create an analysis to acquire explicitly labeled sample weather cells. Forecast
                  scrubbing will keep arrival-risk results unchanged.
                </p>
              </section>
            )}
          </div>
          {analysis && selected ? (
            <CheckpointInspector
              analysis={analysis}
              route={selected}
              checkpoint={checkpoint}
              onCheckpoints={() => setDialog('checkpoints')}
              onSources={() => setDialog('sources')}
            />
          ) : (
            <aside className="panel empty-inspector">
              <span className="eyebrow accent">Intelligence for every mile</span>
              <h2>Every risk has a reason.</h2>
              <p>
                Source time, missing coverage, exact thresholds and distance exposure belong beside
                the map.
              </p>
              <p>
                A route selection is inspection. Only the backend identifies a preferred candidate.
              </p>
            </aside>
          )}
        </div>
      </main>
      <footer className="footer">
        <span>
          {live ? (
            <>
              TomTom ·{' '}
              <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
                Open-Meteo
              </a>{' '}
              / DWD ·{' '}
              <a
                href="https://creativecommons.org/licenses/by/4.0/"
                target="_blank"
                rel="noreferrer"
              >
                CC BY 4.0
              </a>
            </>
          ) : (
            'SAMPLE ANALYSIS'
          )}{' '}
          · NATURAL EARTH GEOGRAPHY · VERSIONED POLICY RESULTS
        </span>
        <button className="text-button" onClick={() => setDialog('sources')} disabled={!analysis}>
          Source and policy details <Icon name="arrow" />
        </button>
      </footer>
      <nav className="mobile-nav" aria-label="Mobile dispatch navigation">
        <a
          href="#main"
          onClick={(event) => {
            event.preventDefault()
            scrollWorkspaceTo('main')
          }}
        >
          <Icon name="map" />
          Dispatch
        </a>
        <a
          href="#forecast"
          onClick={(event) => {
            event.preventDefault()
            scrollWorkspaceTo('forecast')
          }}
        >
          <Icon name="clock" />
          Forecast
        </a>
        <a
          href="#inspector"
          onClick={(event) => {
            event.preventDefault()
            scrollWorkspaceTo('inspector')
          }}
        >
          <Icon name="info" />
          Inspect
        </a>
        <button disabled={!analysis} onClick={() => setDialog('summary')}>
          <Icon name="truck" />
          Summary
        </button>
      </nav>
      <Dialog
        open={dialog !== null}
        title={dialog ? dialogTitles[dialog] : ''}
        onClose={closeDialog}
      >
        {dialog === 'trip' && (
          <TripForm
            key={analysis?.id ?? 'draft'}
            initial={analysis ? analysisToTripInput(analysis) : sampleDraft}
            pending={workspace.analysisPending}
            onSubmit={(input) => {
              void analyze(input).then((result) => {
                if (result) setDialog(null)
              })
            }}
            errorMessage={workspace.error?.message}
            onDirty={markStale}
          />
        )}
        {dialog === 'compare' && analysis && (
          <div className="dialog-route-list">
            <p className="sample-disclosure">
              These are the same backend results shown in Dispatch Canvas. Selecting a route changes
              inspection only.
            </p>
            {analysis.routes.map((route) => (
              <RouteCard
                key={route.id}
                route={route}
                selected={route.id === state.selectedRouteId}
                preferred={route.id === analysis.recommendation.route_id}
                onSelect={() => {
                  selectRoute(route.id)
                  setDialog(null)
                }}
              />
            ))}
          </div>
        )}
        {dialog === 'checkpoints' && selected && (
          <CheckpointTable
            route={selected}
            selectedId={state.selectedCheckpointId}
            onSelect={(id) => {
              selectCheckpoint(selected.id, id)
              setDialog(null)
            }}
          />
        )}
        {dialog === 'sources' && analysis && selected && (
          <SourceDetails analysis={analysis} checkpoint={checkpoint} route={selected} />
        )}
        {dialog === 'summary' && analysis && (
          <div className="driver-summary">
            <span className="sample">{live ? 'LIVE FORECAST · ASSESSMENT' : 'SAMPLE DATA'}</span>
            <h2>
              {preferred
                ? `Route ${preferred.code} preferred in this ${live ? 'analysis' : 'sample'}`
                : 'No verified travel recommendation'}
            </h2>
            <p>{analysis.recommendation.reason}</p>
            {preferred && (
              <>
                <p>
                  {number(preferred.distance_mi)} miles · {duration(preferred.duration_seconds)}{' '}
                  driving
                </p>
                <ExposureBreakdown route={preferred} detailed />
                <h3>Weather to discuss before departure</h3>
                {preferred.checkpoints
                  .filter((point) => point.overall_risk !== 'low')
                  .slice(0, 6)
                  .map((point) => (
                    <p key={point.id}>
                      {point.label} · mile {number(point.distance_mi)} ·{' '}
                      {riskLabels[point.overall_risk]}
                    </p>
                  ))}
              </>
            )}
            <p className="sample-disclosure">
              {live
                ? 'Read-only assessment briefing. Forecast uncertainty and the provider snowfall approximation apply; no travel or navigation assurance.'
                : 'Read-only sample briefing. Review while parked. Hypothetical weather and illustrated routes provide no travel or navigation assurance.'}
            </p>
          </div>
        )}
      </Dialog>
    </>
  )
}
