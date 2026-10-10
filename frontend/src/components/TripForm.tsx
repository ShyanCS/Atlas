import { useState, type FormEvent } from 'react'
import type { TripInput } from '../contracts/types'
import { defaultTrip } from '../contracts/defaults'
import { Icon } from './Icon'
import { LocationPicker } from './LocationPicker'

function nextDeparture(zone: string) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: zone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
    .format(new Date(Date.now() + 3600000))
    .replace(' ', 'T')
}

export function TripForm({
  initial = defaultTrip,
  pending,
  onSubmit,
  errorMessage,
  onDirty,
  curatedExample = false,
  startWithLive = false,
}: {
  initial?: TripInput
  pending: boolean
  onSubmit: (trip: TripInput) => void
  errorMessage?: string | undefined
  onDirty?: () => void
  curatedExample?: boolean
  startWithLive?: boolean
}) {
  const [departure, setDeparture] = useState(
    startWithLive && initial.mode !== 'live'
      ? nextDeparture(initial.origin_timezone)
      : (initial.departure_local?.slice(0, 16) ?? '2026-10-10T06:00'),
  )
  const [load, setLoad] = useState(String(initial.load_weight_lb))
  const [interval, setInterval] = useState<10 | 25 | 50>(
    initial.checkpoint_interval_miles as 10 | 25 | 50,
  )
  const [scenario, setScenario] = useState(initial.scenario)
  const [mode, setMode] = useState<'sample' | 'live'>(
    startWithLive || initial.mode === 'live' ? 'live' : 'sample',
  )
  const [origin, setOrigin] = useState(initial.origin)
  const [destination, setDestination] = useState(initial.destination)
  const [originReady, setOriginReady] = useState(true)
  const [destinationReady, setDestinationReady] = useState(true)
  const [zone, setZone] = useState(initial.origin_timezone)
  const [vehicleWeight, setVehicleWeight] = useState(
    String(initial.truck_profile?.current_weight_kg ?? 36000),
  )
  const [height, setHeight] = useState(String(initial.truck_profile?.height_m ?? '4.1'))
  const [width, setWidth] = useState(String(initial.truck_profile?.width_m ?? '2.6'))
  const [length, setLength] = useState(String(initial.truck_profile?.length_m ?? '21'))
  const [fold, setFold] = useState(
    initial.departure_fold == null ? '' : String(initial.departure_fold),
  )
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({
      mode,
      origin: mode === 'live' ? origin : initial.origin,
      destination: mode === 'live' ? destination : initial.destination,
      origin_timezone: mode === 'live' ? zone : initial.origin_timezone,
      departure_local: departure.length === 16 ? `${departure}:00` : departure,
      load_weight_lb: load,
      checkpoint_interval_miles: interval,
      scenario,
      ...(mode === 'live'
        ? {
            truck_profile: {
              current_weight_kg: Number(vehicleWeight),
              height_m: height,
              width_m: width,
              length_m: length,
            },
          }
        : {}),
      ...(fold === '' ? {} : { departure_fold: Number(fold) as 0 | 1 }),
    })
  }
  return (
    <form className="trip-form" onSubmit={submit} onChange={onDirty}>
      <div className="field">
        <label htmlFor="analysis-mode">Trip source</label>
        <select
          id="analysis-mode"
          value={mode}
          disabled={pending}
          onChange={(event) => {
            const next = event.target.value as 'sample' | 'live'
            setMode(next)
            if (next === 'live' && initial.mode !== 'live') {
              setDeparture(nextDeparture(zone))
            }
            if (next === 'sample' && curatedExample) {
              setDeparture(initial.departure_local?.slice(0, 16) ?? '2026-10-10T06:00')
              setLoad(String(initial.load_weight_lb))
              setInterval(initial.checkpoint_interval_miles as 10 | 25 | 50)
              setFold(initial.departure_fold == null ? '' : String(initial.departure_fold))
            }
          }}
        >
          <option value="sample">Built-in example trip</option>
          <option value="live">Plan a route</option>
        </select>
      </div>
      {mode === 'live' ? (
        <>
          <LocationPicker
            label="Origin"
            value={origin}
            onSelect={setOrigin}
            onValidity={setOriginReady}
            disabled={pending}
          />
          <LocationPicker
            label="Destination"
            value={destination}
            onSelect={setDestination}
            onValidity={setDestinationReady}
            disabled={pending}
          />
        </>
      ) : (
        <>
          <p className="sample-disclosure">
            Explore Chicago–Atlanta with illustrative routes and weather.{' '}
            {curatedExample &&
              'Trip parameters are preset; select Plan a route to enter your own trip.'}
          </p>
          <div className="field">
            <label htmlFor="origin">Origin</label>
            <input id="origin" value="Chicago, Illinois" readOnly />
          </div>
          <div className="field">
            <label htmlFor="destination">Destination</label>
            <input id="destination" value="Atlanta, Georgia" readOnly />
          </div>
        </>
      )}
      <div className="form-two">
        <div className="field">
          <label htmlFor="departure">Local departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            onChange={(event) => {
              setDeparture(event.target.value)
              setFold('')
            }}
            required
            readOnly={mode === 'sample' && curatedExample}
          />
        </div>
        <div className="field">
          <label htmlFor="cargo">Cargo load · pounds</label>
          <input
            id="cargo"
            type="number"
            min="0"
            step="0.01"
            value={load}
            onChange={(event) => setLoad(event.target.value)}
            required
            readOnly={mode === 'sample' && curatedExample}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor="zone">Origin time zone</label>
        <select
          id="zone"
          value={mode === 'live' ? zone : initial.origin_timezone}
          disabled={mode === 'sample' || pending}
          onChange={(event) => {
            setZone(event.target.value)
            setFold('')
          }}
        >
          {[
            'America/Chicago',
            'America/New_York',
            'America/Denver',
            'America/Los_Angeles',
            'America/Phoenix',
          ].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <small>Date-specific offsets and DST are resolved by the backend.</small>
      </div>
      {mode === 'live' && (
        <fieldset className="field">
          <legend>Truck physical profile · verify before submission</legend>
          <small>
            Illustrative defaults. Cargo below is a separate risk input; total vehicle weight must
            include truck, trailer and cargo.
          </small>
          <div className="form-two">
            <div className="field">
              <label htmlFor="vehicle-weight">Total vehicle weight · kg</label>
              <input
                id="vehicle-weight"
                type="number"
                min="1"
                max="100000"
                step="1"
                value={vehicleWeight}
                required
                onChange={(e) => setVehicleWeight(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="vehicle-height">Height · m</label>
              <input
                id="vehicle-height"
                type="number"
                min="0.1"
                max="10"
                step="0.01"
                value={height}
                required
                onChange={(e) => setHeight(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="vehicle-width">Width · m</label>
              <input
                id="vehicle-width"
                type="number"
                min="0.1"
                max="10"
                step="0.01"
                value={width}
                required
                onChange={(e) => setWidth(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="vehicle-length">Length · m</label>
              <input
                id="vehicle-length"
                type="number"
                min="0.1"
                max="50"
                step="0.01"
                value={length}
                required
                onChange={(e) => setLength(e.target.value)}
              />
            </div>
          </div>
        </fieldset>
      )}
      <details className="form-details">
        <summary>Time and truck assumptions</summary>
        <div className="field">
          <label htmlFor="fold">Repeated daylight-saving time</label>
          <select
            id="fold"
            value={fold}
            disabled={mode === 'sample' && curatedExample}
            onChange={(event) => setFold(event.target.value)}
          >
            <option value="">Require a choice if ambiguous</option>
            <option value="0">First occurrence</option>
            <option value="1">Second occurrence</option>
          </select>
        </div>
        <p>
          Cargo is distinct from total vehicle weight.{' '}
          {mode === 'sample'
            ? 'Example routes are illustrative and have no validated road restrictions.'
            : 'Truck routing validates provider sections and warnings; it does not certify road safety or dock access.'}{' '}
          Stops, rest, and duty breaks are excluded from modeled driving time.
        </p>
      </details>
      <fieldset className="field">
        <legend>Checkpoint interval</legend>
        <div className="interval-options">
          {([10, 25, 50] as const).map((value) => (
            <label key={value} className={interval === value ? 'selected' : ''}>
              <input
                type="radio"
                name="interval"
                value={value}
                checked={interval === value}
                disabled={mode === 'sample' && curatedExample}
                onChange={() => setInterval(value)}
              />
              {value} mi
            </label>
          ))}
        </div>
      </fieldset>
      {mode === 'sample' && (
        <div className="field">
          <label htmlFor="scenario">Weather scenario</label>
          <select
            id="scenario"
            value={scenario}
            onChange={(event) => setScenario(event.target.value as TripInput['scenario'])}
          >
            <option value="complete">Complete weather · compare exposure</option>
            <option value="partial">Missing snowfall · Unknown coverage</option>
            <option value="no-travel">Known No Travel · recommendation withheld</option>
          </select>
        </div>
      )}
      {errorMessage && (
        <p className="form-error" role="alert">
          {errorMessage}
        </p>
      )}
      {mode === 'live' && (!originReady || !destinationReady) && (
        <p role="status">
          Select a matching location before analyzing. Draft search text is not a committed
          endpoint.
        </p>
      )}
      <button
        className="btn primary wide"
        type="submit"
        disabled={pending || (mode === 'live' && (!originReady || !destinationReady))}
      >
        <Icon name="refresh" />
        {pending
          ? mode === 'live'
            ? 'Acquiring routes and weather…'
            : 'Loading routes…'
          : mode === 'live'
            ? 'Analyze Route'
            : 'Explore Routes'}
      </button>
    </form>
  )
}
