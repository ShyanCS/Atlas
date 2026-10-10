import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SourceDetails } from './CheckpointInspector'
import { completeAnalysis } from '../test/fixtures'

describe('source disclosures survive product copy refinement', () => {
  it('clearly identifies illustrative demo data', () => {
    render(<SourceDetails analysis={completeAnalysis} route={completeAnalysis.routes[0]!} />)
    expect(screen.getByText(/Demo Mode · illustrative weather/)).toBeVisible()
    expect(screen.getByText(/not live forecasts/)).toBeVisible()
  })

  it('keeps approximation, permission scope, uncertainty and attribution accessible', () => {
    // Authored UI fixture only; this is not provider data or a completed live run.
    const analysis = {
      ...completeAnalysis,
      mode: 'live' as const,
      sample_data: false,
      warnings: ['SOURCE_UNCERTAINTY_WARNING'],
    }
    render(<SourceDetails analysis={analysis} route={analysis.routes[0]!} />)
    expect(screen.getByText(/approximate fixed 7:1 relationship/)).toBeVisible()
    expect(screen.getByText(/personal noncommercial use/)).toBeVisible()
    expect(screen.getByText(/Model initialization is not exposed/)).toBeVisible()
    expect(screen.getByText('SOURCE_UNCERTAINTY_WARNING')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Weather data by Open-Meteo' })).toHaveAttribute(
      'href',
      'https://open-meteo.com/',
    )
    expect(screen.getByRole('link', { name: 'CC BY 4.0' })).toBeVisible()
  })
})
