import { useState } from 'react'
import { setAssessmentAccessCode } from '../api/access'

/** Contextual authorization for an explicitly denied operation; never an entry gate. */
export function PrivatePlanningAccess() {
  const [value, setValue] = useState('')
  const [message, setMessage] = useState('')
  return (
    <details>
      <summary>Private planning access</summary>
      <p>
        If the owner has provided planning access, set it for this tab. The server still determines
        availability and permission.
      </p>
      <div className="field">
        <label htmlFor="planning-access">Planning access</label>
        <input
          id="planning-access"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          maxLength={256}
          onChange={(event) => setValue(event.target.value)}
        />
      </div>
      <button
        type="button"
        className="btn"
        onClick={() => {
          const code = value.trim()
          if (code.length < 24 || code.length > 256) {
            setMessage('Enter the planning access provided by the owner.')
            return
          }
          setAssessmentAccessCode(code)
          setValue('')
          setMessage(
            'Access set for this tab. Select Analyze Route to request planning; no request has been sent.',
          )
        }}
      >
        Set planning access
      </button>
      {message && <p role="status">{message}</p>}
    </details>
  )
}
