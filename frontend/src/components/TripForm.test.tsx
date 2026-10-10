import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TripForm } from './TripForm'

describe('trip input contract', () => {
  it('offers the real planning workflow first while restoring fixed public-example parameters', () => {
    render(<TripForm pending={false} onSubmit={vi.fn()} curatedExample startWithLive />)
    expect(screen.getByLabelText('Trip source')).toHaveValue('live')
    fireEvent.change(screen.getByLabelText('Cargo load · pounds'), {
      target: { value: '40000.01' },
    })
    fireEvent.change(screen.getByLabelText('Trip source'), { target: { value: 'sample' } })
    expect(screen.getByLabelText('Cargo load · pounds')).toHaveValue(24000)
    expect(screen.getByLabelText('Cargo load · pounds')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Local departure')).toHaveAttribute('readonly')
    expect(screen.getByRole('radio', { name: '10 mi' })).toBeDisabled()
    expect(screen.getByLabelText('Weather scenario')).toBeEnabled()
  })
  it('sends an explicit wall time and DST occurrence without guessing a UTC instant', () => {
    const submit = vi.fn()
    render(<TripForm pending={false} onSubmit={submit} />)
    fireEvent.change(screen.getByLabelText('Local departure'), {
      target: { value: '2026-11-01T01:30' },
    })
    fireEvent.change(screen.getByLabelText('Repeated daylight-saving time'), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Cargo load · pounds'), {
      target: { value: '40000.01' },
    })
    fireEvent.click(screen.getByRole('radio', { name: '50 mi' }))
    fireEvent.click(screen.getByRole('button', { name: 'Explore Routes' }))
    expect(submit).toHaveBeenCalledOnce()
    expect(submit.mock.calls[0]?.[0]).toMatchObject({
      mode: 'sample',
      departure_local: '2026-11-01T01:30:00',
      departure_fold: 1,
      origin_timezone: 'America/Chicago',
      load_weight_lb: '40000.01',
      checkpoint_interval_miles: 50,
    })
    expect(submit.mock.calls[0]?.[0]).not.toHaveProperty('departure_at')
  })

  it('discloses the fixed sample corridor and preserves a partial-data scenario', () => {
    const submit = vi.fn()
    render(<TripForm pending={false} onSubmit={submit} />)
    expect(screen.getByLabelText('Origin')).toHaveAttribute('readonly')
    expect(screen.getByText(/illustrative routes and weather/)).toBeVisible()
    fireEvent.change(screen.getByLabelText('Weather scenario'), {
      target: { value: 'partial' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Explore Routes' }))
    expect(submit.mock.calls[0]?.[0]).toMatchObject({
      scenario: 'partial',
      origin: { name: 'Chicago, IL' },
      destination: { name: 'Atlanta, GA' },
    })
  })

  it('discloses approximation and separates physical truck weight from cargo in live mode', () => {
    const submit = vi.fn()
    render(<TripForm pending={false} onSubmit={submit} />)
    fireEvent.change(screen.getByLabelText('Trip source'), { target: { value: 'live' } })
    expect(screen.getByLabelText('Total vehicle weight · kg')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Total vehicle weight · kg'), {
      target: { value: '36000' },
    })
    fireEvent.change(screen.getByLabelText('Cargo load · pounds'), {
      target: { value: '30000.01' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analyze Route' }))
    expect(submit.mock.calls[0]?.[0]).toMatchObject({
      mode: 'live',
      load_weight_lb: '30000.01',
      truck_profile: { current_weight_kg: 36000 },
    })
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Uncommitted draft' } })
    expect(screen.getByRole('button', { name: 'Analyze Route' })).toBeDisabled()
  })
})
