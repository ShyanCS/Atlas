export function number(value: string | number | null | undefined, digits = 1): string {
  if (value == null) return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(numeric)
    : '—'
}

export function duration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}

export function clock(instant: string, zone = 'America/New_York'): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: zone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(new Date(instant))
}

export function datedClock(instant: string, zone = 'America/Chicago'): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: zone,
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(new Date(instant))
}

export const riskLabels: Record<string, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unknown: 'Unknown',
}
export const riskColors: Record<string, string> = {
  low: '#34BFA9',
  moderate: '#E9C46A',
  high: '#F39A53',
  severe: '#E76666',
  no_travel: '#CF89F0',
  unknown: '#91A3AD',
}
export const routeColors: Record<string, string> = { A: '#5D9BFF', B: '#B18AFF', C: '#39C6C3' }
