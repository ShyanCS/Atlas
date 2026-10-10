import { useEffect, useState, type ReactNode } from 'react'
import { atlasApi } from '../api/client'
import { setAssessmentAccessCode } from '../api/access'
import { toApiError } from '../api/errors'
import { AtlasBrand } from './Icon'

/** One explicit readiness/access check; never automatically submits an analysis. */
export function AssessmentGateway({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'locked' | 'ready' | 'error'>('checking')
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => setSlow(true), 6000)
    void atlasApi.getHealth(controller.signal).then(
      (health) => setState(health.assessment_access_required ? 'locked' : 'ready'),
      (error) => {
        if (!controller.signal.aborted) {
          setState('error')
          setMessage(toApiError(error).message)
        }
      },
    )
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [])
  if (state === 'ready') return <>{children}</>
  const unlock = async () => {
    setAssessmentAccessCode(code)
    setState('checking')
    setMessage('')
    try {
      await atlasApi.getScenarios()
      setCode('')
      setState('ready')
    } catch (error) {
      setAssessmentAccessCode('')
      setState('locked')
      setMessage(toApiError(error).message)
    }
  }
  return (
    <main className="assessment-gateway">
      <section className="panel" aria-labelledby="assessment-access-title">
        <AtlasBrand />
        <p className="eyebrow">WEATHER INTELLIGENCE</p>
        <h1 id="assessment-access-title">
          {state === 'locked' ? 'Access Spotter Atlas' : 'Connecting to Dispatch Canvas'}
        </h1>
        {state === 'checking' && (
          <p role="status">
            {slow
              ? 'The free backend or database may be waking. This can take about a minute. No trip has been submitted.'
              : 'Connecting to your workspace…'}
          </p>
        )}
        {state === 'locked' && (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void unlock()
            }}
          >
            <label htmlFor="reviewer-code">Private reviewer access code</label>
            <input
              id="reviewer-code"
              type="password"
              autoComplete="off"
              minLength={24}
              maxLength={256}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
            />
            <p className="quiet">
              Your code stays in this tab's memory. Enter it again after a reload. Live forecasts
              require the configured source permissions.
            </p>
            <button className="btn primary" type="submit">
              Open Dispatch Canvas
            </button>
          </form>
        )}
        {message && <p role="alert">{message}</p>}
        {state === 'error' && (
          <button className="btn" onClick={() => window.location.reload()}>
            Retry connection
          </button>
        )}
      </section>
    </main>
  )
}
