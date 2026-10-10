import { Icon } from './Icon'
import { useEffect, useState } from 'react'

export function AnalysisStatus({
  pending,
  error,
  stale,
  noRecommendation,
  onRetry,
}: {
  pending: boolean
  error?: string | undefined
  stale: boolean
  noRecommendation: boolean
  onRetry: () => void
}) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(pending), 6000)
    return () => {
      clearTimeout(timer)
      setSlow(false)
    }
  }, [pending])
  if (!pending && !error && !stale && !noRecommendation) return null
  const title = pending
    ? 'Analyzing trip'
    : error
      ? 'Analysis could not complete'
      : stale
        ? 'Previous analysis · draft changed'
        : 'No verified travel recommendation'
  const message = pending
    ? slow
      ? 'Connecting to the workspace. The server may take about a minute to wake; your inputs are retained.'
      : 'Matching checkpoint weather and comparing route exposure. Your recommendation appears when analysis completes.'
    : (error ??
      (stale
        ? 'The saved snapshot still belongs to its original inputs. Re-analyze to evaluate your changes.'
        : 'Inspect No Travel and missing-weather reasons. A blocked candidate is available for inspection and cannot become preferred through selection.'))
  return (
    <section
      className={`status-banner ${error || noRecommendation ? 'warning' : ''}`}
      role={error || noRecommendation ? 'alert' : 'status'}
    >
      <Icon name={pending ? 'refresh' : 'alert'} />
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
      {!pending && (
        <button className="btn" onClick={onRetry}>
          Review trip
        </button>
      )}
    </section>
  )
}
