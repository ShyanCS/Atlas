import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { getAssessmentAccessCode, setAssessmentAccessCode } from '../api/access'
import { PrivatePlanningAccess } from './PrivatePlanningAccess'

afterEach(() => {
  cleanup()
  setAssessmentAccessCode('')
})
describe('contextual private planning access', () => {
  it('sets tab-memory authorization without sending a request or retaining the input', () => {
    render(<PrivatePlanningAccess />)
    fireEvent.click(screen.getByText('Private planning access'))
    const input = screen.getByLabelText('Planning access')
    expect(input).toHaveAttribute('type', 'password')
    fireEvent.change(input, { target: { value: 'authored-private-planning-test-code' } })
    fireEvent.click(screen.getByRole('button', { name: 'Set planning access' }))
    expect(getAssessmentAccessCode()).toBe('authored-private-planning-test-code')
    expect(input).toHaveValue('')
    expect(screen.getByRole('status')).toHaveTextContent('no request has been sent')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
  it('rejects an invalid value without replacing existing tab access', () => {
    setAssessmentAccessCode('authored-existing-planning-code')
    render(<PrivatePlanningAccess />)
    fireEvent.click(screen.getByText('Private planning access'))
    fireEvent.change(screen.getByLabelText('Planning access'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Set planning access' }))
    expect(getAssessmentAccessCode()).toBe('authored-existing-planning-code')
    expect(screen.getByRole('status')).toHaveTextContent('provided by the owner')
  })
})
