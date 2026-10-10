import { useState } from 'react'
import { atlasApi, type GeocodePlace } from '../api/client'
import { toApiError } from '../api/errors'
import type { Location } from '../contracts/types'

/** Explicit search + committed selection: never requests on every keystroke. */
export function LocationPicker({
  label,
  value,
  onSelect,
  disabled,
  onValidity,
}: {
  label: string
  value: Location
  onSelect: (place: Location) => void
  disabled: boolean
  onValidity?: (ready: boolean) => void
}) {
  const [text, setText] = useState(value.name)
  const [results, setResults] = useState<GeocodePlace[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const id = `live-${label.toLowerCase()}`
  const search = async () => {
    setPending(true)
    setError('')
    try {
      const places = await atlasApi.geocode(text)
      setResults(places)
      if (!places.length) setError('No matching location. Try a more specific US address.')
    } catch (error) {
      setError(toApiError(error).message)
    } finally {
      setPending(false)
    }
  }
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          onValidity?.(event.target.value === value.name)
        }}
        maxLength={200}
        disabled={disabled || pending}
      />
      <button
        className="btn"
        type="button"
        disabled={disabled || pending || !text.trim()}
        onClick={() => {
          void search()
        }}
      >
        {pending ? 'Searching…' : `Search ${label.toLowerCase()}`}
      </button>
      <div className="location-results" aria-label={`${label} matches`}>
        {results.map((place, index) => (
          <button
            type="button"
            className="btn"
            key={index}
            onClick={() => {
              onSelect({ name: place.name, latitude: place.latitude, longitude: place.longitude })
              setText(place.name)
              setResults([])
              onValidity?.(true)
            }}
          >
            {place.name}
          </button>
        ))}
      </div>
      <small>
        Committed: {value.name} · {value.latitude}, {value.longitude}. Geocoding does not verify
        dock access.
      </small>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </div>
  )
}
