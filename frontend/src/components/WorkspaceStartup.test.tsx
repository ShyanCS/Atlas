import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { atlasApi } from '../api/client'
import { ApiError } from '../api/errors'
import { completeAnalysis, scenariosFixture, windFrame } from '../test/fixtures'
import { getAssessmentAccessCode, setAssessmentAccessCode } from '../api/access'

vi.mock('./OperationalMap', () => ({ OperationalMap: () => <div>Operational map</div> }))
afterEach(() => {
  vi.restoreAllMocks()
  setAssessmentAccessCode('')
})
describe('direct anonymous workspace startup', () => {
  it('opens the shell immediately and loads the genuine example contract without a code or POST', async () => {
    vi.spyOn(atlasApi, 'getScenarios').mockResolvedValue(scenariosFixture)
    const example = vi.spyOn(atlasApi, 'getExample').mockResolvedValue(completeAnalysis)
    const post = vi.spyOn(atlasApi, 'createAnalysis')
    vi.spyOn(atlasApi, 'getFrame').mockResolvedValue(windFrame)
    render(<App />)
    expect(screen.getByText('Operational map')).toBeInTheDocument()
    expect(screen.queryByLabelText('Private reviewer access code')).not.toBeInTheDocument()
    expect(await screen.findByText('Example trip')).toBeVisible()
    expect(example).toHaveBeenCalledOnce()
    expect(post).not.toHaveBeenCalled()
    expect(getAssessmentAccessCode()).toBe('')
    expect(screen.queryByText('DEMO MODE')).not.toBeInTheDocument()
  })
  it('keeps the shell usable on connection failure and does not automatically retry', async () => {
    const scenarios = vi
      .spyOn(atlasApi, 'getScenarios')
      .mockRejectedValue(
        new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'Connection unavailable' }),
      )
    const example = vi.spyOn(atlasApi, 'getExample')
    render(<App />)
    expect(screen.getByText('Operational map')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Connection unavailable'),
    )
    expect(scenarios).toHaveBeenCalledOnce()
    expect(example).not.toHaveBeenCalled()
  })
})
