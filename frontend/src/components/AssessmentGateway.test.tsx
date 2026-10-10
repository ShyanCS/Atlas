import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AssessmentGateway } from './AssessmentGateway'
import { atlasApi } from '../api/client'
import { ApiError } from '../api/errors'
import { getAssessmentAccessCode, setAssessmentAccessCode } from '../api/access'

afterEach(() => {
  vi.restoreAllMocks()
  setAssessmentAccessCode('')
})
describe('assessment access and cold start', () => {
  it('allows local sample access without a reviewer or provider key', async () => {
    vi.spyOn(atlasApi, 'getHealth').mockResolvedValue({
      assessment_access_required: false,
      live_available: false,
    })
    render(
      <AssessmentGateway>
        <p>Workspace ready</p>
      </AssessmentGateway>,
    )
    expect(await screen.findByText('Workspace ready')).toBeInTheDocument()
  })
  it('requires explicit reviewer code and retains it only in memory', async () => {
    vi.spyOn(atlasApi, 'getHealth').mockResolvedValue({
      assessment_access_required: true,
      live_available: false,
    })
    const scenarios = vi.spyOn(atlasApi, 'getScenarios').mockResolvedValue({} as never)
    render(
      <AssessmentGateway>
        <p>Workspace ready</p>
      </AssessmentGateway>,
    )
    fireEvent.change(await screen.findByLabelText('Private reviewer access code'), {
      target: { value: 'authored-reviewer-code-for-testing' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Open Dispatch Canvas' }))
    expect(await screen.findByText('Workspace ready')).toBeInTheDocument()
    expect(scenarios).toHaveBeenCalledTimes(1)
    expect(getAssessmentAccessCode()).toBe('authored-reviewer-code-for-testing')
  })
  it('shows backend failure and offers only manual retry', async () => {
    const health = vi
      .spyOn(atlasApi, 'getHealth')
      .mockRejectedValue(
        new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'Backend is unavailable' }),
      )
    render(
      <AssessmentGateway>
        <p>Workspace ready</p>
      </AssessmentGateway>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend is unavailable')
    expect(screen.getByRole('button', { name: 'Retry connection' })).toBeInTheDocument()
    expect(health).toHaveBeenCalledTimes(1)
  })
})
