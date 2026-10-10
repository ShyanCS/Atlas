const paths = {
  arrow: 'M4 9h10m-4-4 4 4-4 4',
  pin: 'M14 7c0 4-5 8-5 8S4 11 4 7a5 5 0 1 1 10 0ZM9 7h.01',
  clock: 'M9 4v5l3 2M16 9a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  wind: 'M2 6h10a2 2 0 1 0-2-2M2 9h13a2 2 0 1 1-2 2M2 12h5',
  rain: 'M4 10a4 4 0 1 1 3-7 4 4 0 1 1 7 7ZM5 13l-1 2m5-2-1 2m5-2-1 2',
  snow: 'M9 2v14M3 5l12 8M3 13l12-8M6 3l3 2 3-2M6 15l3-2 3 2',
  check: 'M3 9l4 4 8-9',
  info: 'M9 8v5M9 5h.01M16 9a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  stop: 'M6 2h6l4 4v6l-4 4H6l-4-4V6ZM9 5v5m0 3h.01',
  layers: 'M2 6l7-4 7 4-7 4ZM2 10l7 4 7-4M2 14l7 4 7-4',
  compass: 'M9 1v2M9 15v2M1 9h2m12 0h2M12 6l-2 4-4 2 2-4Z',
  truck: 'M2 4h9v8H2Zm9 3h3l3 3v2h-6M5 14a2 2 0 1 0 0-.1M14 14a2 2 0 1 0 0-.1',
  edit: 'M3 12l-1 4 4-1L15 6l-3-3ZM10 5l3 3',
  map: 'M2 4l4-2 6 2 4-2v12l-4 2-6-2-4 2ZM6 2v12m6-10v12',
  chart: 'M2 2v14h14M4 12l4-5 3 3 4-7',
  alert: 'M9 2l8 14H1ZM9 7v4m0 3h.01',
  close: 'M4 4l10 10M4 14 14 4',
  refresh: 'M15 6a6 6 0 1 0 0 6M15 2v4h-4',
} as const

export type IconName = keyof typeof paths
export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return (
    <svg className={`icon ${className}`} viewBox="0 0 18 18" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  )
}

export function AtlasBrand() {
  return (
    <div className="brand" aria-label="Spotter Atlas">
      <svg viewBox="0 0 30 30" aria-hidden="true">
        <path d="M3 25 14 4h3l10 21M9 18h14" stroke="#35d6c5" strokeWidth="2.1" fill="none" />
        <circle cx="15" cy="17" r="2.7" fill="#eff6f8" />
      </svg>
      <span>Spotter Atlas</span>
    </div>
  )
}
