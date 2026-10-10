import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { type GeoJSONSource, type Map as LibreMap } from 'maplibre-gl'
import type { FeatureCollection, LineString, Point, Polygon } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Analysis, Checkpoint, WeatherFrame } from '../contracts/types'
import { Icon } from './Icon'
import { clock, number, riskColors, riskLabels, routeColors } from './format'

// MapLibre 6 requires a bundler-managed worker URL. Vite bundles its imports locally.
maplibregl.setWorkerUrl(workerUrl)

export type MapMode = 'arrival-risk' | 'clock-forecast'
type Props = {
  analysis: Analysis | null
  selectedRouteId: string | null
  checkpoint?: Checkpoint | undefined
  mode: MapMode
  frame: WeatherFrame | null
  framePending: boolean
  onMode: (mode: MapMode) => void
  onRoute: (id: string) => void
  onCheckpoint: (routeId: string, id: string) => void
  onCheckpointList: () => void
}
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }
const fieldScales = {
  wind: { unit: 'mph', stops: [0, 20, 40, 60] },
  rain: { unit: 'in/hr', stops: [0, 0.1, 0.5, 1] },
  snow: { unit: 'in/hr', stops: [0, 0.5, 2, 3] },
} as const
const rawPalette = ['#173846', '#279C9C', '#B8D477', '#F3B46A'] as const
function coordinate(point: number[]): [number, number] {
  const longitude = point[0],
    latitude = point[1]
  if (
    longitude === undefined ||
    latitude === undefined ||
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude)
  )
    throw new Error('Malformed map coordinate')
  return [longitude, latitude]
}
function rawColor(value: string | null, variable: keyof typeof fieldScales): string {
  if (value === null) return '#91A3AD'
  // Display palette only. Classification, exposure and ranking are never calculated here.
  const stops = fieldScales[variable].stops
  const n = Number(value)
  return rawPalette[n >= stops[3] ? 3 : n >= stops[2] ? 2 : n >= stops[1] ? 1 : 0]
}

function updateMap(map: LibreMap, props: Props) {
  if (!map.getSource('routes')) return
  const routes: FeatureCollection<LineString> = {
    type: 'FeatureCollection',
    features:
      props.analysis?.routes.map((route) => ({
        type: 'Feature',
        geometry: route.geometry as LineString,
        properties: {
          id: route.id,
          color: routeColors[route.code],
          selected: route.id === props.selectedRouteId,
        },
      })) ?? [],
  }
  const spans: FeatureCollection<LineString> = {
    type: 'FeatureCollection',
    features:
      props.analysis?.routes.flatMap((route) =>
        route.risk_spans.map((span) => ({
          type: 'Feature' as const,
          geometry: span.geometry as LineString,
          properties: {
            id: route.id,
            color: riskColors[span.classification],
            selected: route.id === props.selectedRouteId,
          },
        })),
      ) ?? [],
  }
  const points: FeatureCollection<Point> = {
    type: 'FeatureCollection',
    features:
      props.analysis?.routes.flatMap((route) =>
        route.checkpoints.map((checkpoint) => ({
          type: 'Feature' as const,
          geometry: {
            type: 'Point' as const,
            coordinates: [
              Number(checkpoint.coordinate.longitude),
              Number(checkpoint.coordinate.latitude),
            ],
          },
          properties: {
            route_id: route.id,
            id: checkpoint.id,
            color: riskColors[checkpoint.overall_risk],
            selected: route.id === props.selectedRouteId,
            inspected: checkpoint.id === props.checkpoint?.id,
            endpoint: checkpoint.index === 0 || checkpoint.label === 'Finish',
          },
        })),
      ) ?? [],
  }
  const cells: FeatureCollection<Polygon> = {
    type: 'FeatureCollection',
    features:
      props.frame?.cells.map((cell) => ({
        type: 'Feature',
        geometry: cell.geometry as Polygon,
        properties: {
          color: rawColor(cell.measurement.value, props.frame!.variable),
          missing: cell.measurement.value === null,
        },
      })) ?? [],
  }
  for (const [id, data] of [
    ['routes', routes],
    ['spans', spans],
    ['checkpoints', points],
    ['cells', cells],
  ] as const) {
    ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
  }
  map.setLayoutProperty(
    'risk-spans',
    'visibility',
    props.mode === 'arrival-risk' ? 'visible' : 'none',
  )
  map.setLayoutProperty(
    'weather-cells',
    'visibility',
    props.mode === 'clock-forecast' ? 'visible' : 'none',
  )
  map.setLayoutProperty(
    'missing-cells',
    'visibility',
    props.mode === 'clock-forecast' ? 'visible' : 'none',
  )
}

function fit(map: LibreMap, analysis: Analysis | null) {
  const coordinates = analysis?.routes.flatMap((route) => route.geometry.coordinates) ?? [
    [-88.5, 41.88],
    [-83.5, 33.75],
  ]
  const bounds = new maplibregl.LngLatBounds()
  coordinates.forEach((point) => bounds.extend(coordinate(point)))
  map.fitBounds(bounds, { padding: { top: 90, bottom: 98, left: 40, right: 45 }, duration: 0 })
}

function FallbackMap({ analysis, selectedRouteId, onRoute, mode, frame }: Props) {
  const live = analysis?.mode === 'live'
  const all = analysis?.routes.flatMap((route) => route.geometry.coordinates) ?? []
  const extent = all.reduce(
    (bounds, p) => [
      Math.min(bounds[0]!, p[0]!),
      Math.max(bounds[1]!, p[0]!),
      Math.min(bounds[2]!, p[1]!),
      Math.max(bounds[3]!, p[1]!),
    ],
    [Infinity, -Infinity, Infinity, -Infinity],
  )
  const west = all.length ? extent[0]! - 0.3 : -94
  const east = all.length ? extent[1]! + 0.3 : -78
  const south = all.length ? extent[2]! - 0.3 : 31
  const north = all.length ? extent[3]! + 0.3 : 43.8
  const project = (point: number[]) => {
    const [lng, lat] = coordinate(point)
    return live
      ? `${((lng - west) / (east - west)) * 1000},${((north - lat) / (north - south)) * 700}`
      : `${((lng + 94) / 16) * 1000},${((43.8 - lat) / 12.8) * 700}`
  }
  return (
    <div className="fallback-map">
      {!live && <img src="/assets/map-base.svg" alt="" />}
      <svg
        viewBox="0 0 1000 700"
        role="group"
        aria-label="Simplified route diagram; use checkpoint list for detailed inspection"
      >
        <defs>
          <pattern
            id="fallback-unknown"
            width="10"
            height="10"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="10" height="10" fill="#293C48" />
            <rect width="2" height="10" fill="#91A3AD" />
          </pattern>
        </defs>
        {mode === 'clock-forecast' &&
          frame?.cells.map((cell) => (
            <polygon
              key={cell.id}
              points={cell.geometry.coordinates[0]?.map(project).join(' ')}
              fill={
                cell.measurement.value === null
                  ? 'url(#fallback-unknown)'
                  : rawColor(cell.measurement.value, frame.variable)
              }
              opacity={0.6}
            />
          ))}
        {analysis?.routes.map((route) => (
          <g key={route.id}>
            <polyline
              points={route.geometry.coordinates.map(project).join(' ')}
              fill="none"
              stroke={routeColors[route.code]}
              strokeWidth={route.id === selectedRouteId ? 11 : 7}
              opacity={0.85}
            />
            {mode === 'arrival-risk' &&
              route.risk_spans.map((span, index) => (
                <polyline
                  key={index}
                  points={span.geometry.coordinates.map(project).join(' ')}
                  fill="none"
                  stroke={riskColors[span.classification]}
                  strokeWidth={route.id === selectedRouteId ? 5 : 3}
                />
              ))}
            <polyline
              points={route.geometry.coordinates.map(project).join(' ')}
              fill="none"
              stroke="transparent"
              strokeWidth="25"
              role="button"
              tabIndex={0}
              aria-label={`Inspect Route ${route.code} in simplified map`}
              onClick={() => onRoute(route.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onRoute(route.id)
                }
              }}
            />
          </g>
        ))}
      </svg>
      <p className="fallback-note">
        <Icon name="info" />
        WebGL unavailable · simplified diagram. All results remain available in cards and checkpoint
        lists.
      </p>
    </div>
  )
}

export function OperationalMap(props: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LibreMap | null>(null)
  const latest = useRef(props)
  const marker = useRef<maplibregl.Marker | null>(null)
  const lastFit = useRef<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const [visualReady, setVisualReady] = useState(false)
  useEffect(() => {
    latest.current = props
  }, [props])

  useEffect(() => {
    if (!container.current) return
    let map: LibreMap
    try {
      map = new maplibregl.Map({
        container: container.current,
        center: [-86, 38],
        zoom: 4.7,
        attributionControl: false,
        cooperativeGestures: true,
        style: {
          version: 8,
          sources: {},
          layers: [
            { id: 'background', type: 'background', paint: { 'background-color': '#10212c' } },
          ],
        },
      })
      mapRef.current = map
    } catch {
      setFailed(true)
      return
    }
    map.on('error', () => setFailed(true))
    map.on('load', () => {
      map.addSource('states', { type: 'geojson', data: '/assets/states.geojson' })
      map.addLayer({
        id: 'state-fills',
        type: 'fill',
        source: 'states',
        paint: { 'fill-color': '#122631', 'fill-opacity': 0.65 },
      })
      map.addLayer({
        id: 'state-borders',
        type: 'line',
        source: 'states',
        paint: { 'line-color': '#35505d', 'line-width': 1 },
      })
      for (const id of ['routes', 'spans', 'checkpoints', 'cells'])
        map.addSource(id, { type: 'geojson', data: empty })
      const pattern = new Uint8Array(12 * 12 * 4)
      for (let y = 0; y < 12; y++)
        for (let x = 0; x < 12; x++) {
          const i = (y * 12 + x) * 4
          const hatch = (x + y) % 8 < 2
          pattern.set(hatch ? [170, 189, 196, 190] : [20, 38, 48, 100], i)
        }
      map.addImage('unknown-hatch', { width: 12, height: 12, data: pattern })
      map.addLayer({
        id: 'weather-cells',
        type: 'fill',
        source: 'cells',
        filter: ['==', ['get', 'missing'], false],
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.62 },
      })
      map.addLayer({
        id: 'missing-cells',
        type: 'fill',
        source: 'cells',
        filter: ['==', ['get', 'missing'], true],
        paint: { 'fill-pattern': 'unknown-hatch', 'fill-opacity': 0.85 },
      })
      map.addLayer({
        id: 'route-casing',
        type: 'line',
        source: 'routes',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['get', 'selected'], 9, 6],
          'line-opacity': ['case', ['get', 'selected'], 0.95, 0.65],
        },
      })
      map.addLayer({
        id: 'risk-spans',
        type: 'line',
        source: 'spans',
        layout: { 'line-cap': 'butt', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['get', 'selected'], 4.5, 3],
          'line-opacity': ['case', ['get', 'selected'], 1, 0.85],
        },
      })
      map.addLayer({
        id: 'route-hit',
        type: 'line',
        source: 'routes',
        paint: { 'line-width': 22, 'line-opacity': 0 },
      })
      map.addLayer({
        id: 'checkpoint-hit',
        type: 'circle',
        source: 'checkpoints',
        minzoom: 6,
        filter: ['==', ['get', 'selected'], true],
        paint: { 'circle-radius': 22, 'circle-opacity': 0 },
      })
      map.addLayer({
        id: 'checkpoint-selected-hit',
        type: 'circle',
        source: 'checkpoints',
        filter: [
          'all',
          ['==', ['get', 'selected'], true],
          ['any', ['get', 'inspected'], ['get', 'endpoint']],
        ],
        paint: { 'circle-radius': 22, 'circle-opacity': 0 },
      })
      map.addLayer({
        id: 'checkpoint-points',
        type: 'circle',
        source: 'checkpoints',
        filter: ['==', ['get', 'selected'], true],
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': ['case', ['get', 'inspected'], 7, 3.5],
          'circle-stroke-color': '#eff6f8',
          'circle-stroke-width': ['case', ['get', 'inspected'], 2, 1],
          'circle-opacity': [
            'step',
            ['zoom'],
            ['case', ['any', ['get', 'inspected'], ['get', 'endpoint']], 1, 0],
            6,
            1,
          ],
          'circle-stroke-opacity': [
            'step',
            ['zoom'],
            ['case', ['any', ['get', 'inspected'], ['get', 'endpoint']], 1, 0],
            6,
            1,
          ],
        },
      })
      for (const [name, lng, lat, kind] of [
        ['Chicago', -87.6298, 41.8781, 'city'],
        ['Atlanta', -84.388, 33.749, 'city'],
        ['Nashville', -86.78, 36.16, 'city'],
        ['Indianapolis', -86.16, 39.77, 'city'],
        ['ILLINOIS', -89.2, 40.1, 'region'],
        ['INDIANA', -85.6, 40.0, 'region'],
        ['OHIO', -82.5, 40.0, 'region'],
        ['KENTUCKY', -84.2, 37.8, 'region'],
        ['TENNESSEE', -85.3, 35.7, 'region'],
        ['GEORGIA', -83.2, 32.9, 'region'],
      ] as const) {
        const label = document.createElement('span')
        label.className = `map-label ${kind}`
        label.textContent = name
        label.setAttribute('aria-hidden', 'true')
        new maplibregl.Marker({ element: label, anchor: 'left', offset: [9, 0] })
          .setLngLat([lng, lat])
          .addTo(map)
      }
      map.on('click', (event) => {
        const checkpoint = map.queryRenderedFeatures(event.point, {
          layers: ['checkpoint-selected-hit', 'checkpoint-hit'],
        })[0]
        if (checkpoint?.properties) {
          latest.current.onCheckpoint(
            String(checkpoint.properties.route_id),
            String(checkpoint.properties.id),
          )
          return
        }
        const route = map.queryRenderedFeatures(event.point, { layers: ['route-hit'] })[0]
        if (route?.properties) latest.current.onRoute(String(route.properties.id))
      })
      map.getCanvas().addEventListener('webglcontextlost', (event) => {
        event.preventDefault()
        setFailed(true)
      })
      map.addControl(
        new maplibregl.AttributionControl({
          customAttribution:
            '<a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener noreferrer">Natural Earth · public domain</a>',
          compact: false,
        }),
        'bottom-right',
      )
      fit(map, latest.current.analysis)
      lastFit.current = latest.current.analysis?.id ?? null
      updateMap(map, latest.current)
      setReady(true)
      map.once('idle', () => setVisualReady(true))
    })
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current)
    return () => {
      observer.disconnect()
      marker.current?.remove()
      marker.current = null
      if (mapRef.current === map) {
        map.remove()
        mapRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || failed) return
    setVisualReady(false)
    updateMap(map, props)
    map.once('idle', () => setVisualReady(true))
    if (props.analysis && lastFit.current !== props.analysis.id) {
      fit(map, props.analysis)
      lastFit.current = props.analysis.id
    }
    marker.current?.remove()
    marker.current = null
    if (props.checkpoint && props.mode === 'arrival-risk') {
      const checkpoint = props.checkpoint
      const node = document.createElement('div')
      node.className = 'map-callout'
      const title = document.createElement('strong')
      title.textContent = `${checkpoint.label} · ${riskLabels[checkpoint.overall_risk]}`
      const detail = document.createElement('span')
      detail.textContent = `Mile ${number(checkpoint.distance_mi)} · ${clock(checkpoint.eta_utc, props.analysis?.mode === 'live' ? 'UTC' : 'America/New_York')}`
      const value = document.createElement('span')
      value.textContent = `${number(checkpoint.measurements.wind.value)} mph ${checkpoint.measurements.wind.provenance.kind === 'synthetic' ? 'sample' : 'forecast'} wind`
      node.append(title, detail, value)
      const location: [number, number] = [
        Number(checkpoint.coordinate.longitude),
        Number(checkpoint.coordinate.latitude),
      ]
      const below = map.project(location).y < 150
      node.classList.toggle('below-point', below)
      marker.current = new maplibregl.Marker({
        element: node,
        anchor: below ? 'top' : 'bottom',
        offset: [0, below ? 14 : -14],
      })
        .setLngLat(location)
        .addTo(map)
    }
  }, [props, ready, failed])

  useEffect(() => {
    if (failed && mapRef.current) {
      marker.current?.remove()
      marker.current = null
      mapRef.current.remove()
      mapRef.current = null
    }
  }, [failed])
  const scale = props.frame ? fieldScales[props.frame.variable] : fieldScales.wind
  return (
    <section
      className="map-box"
      aria-label={
        props.analysis?.mode === 'live'
          ? 'Operational live assessment map'
          : 'Operational sample map'
      }
      data-testid="operational-map"
      data-renderer={failed ? 'fallback' : ready ? 'maplibre' : 'loading'}
      data-visual-ready={failed || visualReady}
    >
      {!failed && <div ref={container} className="map-canvas" />}
      {failed && <FallbackMap {...props} />}
      <div className="map-toolbar">
        <div className="mode-control" role="group" aria-label="Map weather interpretation">
          <button
            aria-pressed={props.mode === 'arrival-risk'}
            onClick={() => props.onMode('arrival-risk')}
          >
            Risk at arrival
          </button>
          <button
            aria-pressed={props.mode === 'clock-forecast'}
            onClick={() => props.onMode('clock-forecast')}
          >
            Forecast at clock time
          </button>
        </div>
      </div>
      <div className="map-controls">
        <button
          className="btn icon-only"
          aria-label="Zoom in"
          disabled={failed}
          onClick={() => mapRef.current?.zoomIn({ duration: 0 })}
        >
          +
        </button>
        <button
          className="btn icon-only"
          aria-label="Zoom out"
          disabled={failed}
          onClick={() => mapRef.current?.zoomOut({ duration: 0 })}
        >
          −
        </button>
        <button
          className="btn icon-only"
          aria-label={props.analysis?.mode === 'live' ? 'Fit live trip' : 'Fit sample trip'}
          disabled={failed}
          onClick={() => mapRef.current && fit(mapRef.current, props.analysis)}
        >
          <Icon name="compass" />
        </button>
        <button
          className="btn icon-only"
          aria-label="Open accessible checkpoint list"
          onClick={props.onCheckpointList}
        >
          <Icon name="layers" />
        </button>
      </div>
      {!props.analysis && (
        <div className="map-empty">
          <Icon name="map" />
          <h2>A clearer view of the road ahead.</h2>
          <p>Create a labeled sample analysis to compare the three illustrated candidates.</p>
        </div>
      )}
      <div className="map-bottom">
        <p>
          {props.analysis?.mode === 'live'
            ? 'LIVE FORECAST · ASSESSMENT ONLY · NOT NAVIGATION'
            : 'SAMPLE ROUTES & WEATHER · NOT NAVIGATION'}
        </p>
        {props.mode === 'arrival-risk' ? (
          <div className="map-legend" aria-label="Arrival-time risk legend">
            {Object.keys(riskLabels).map((key) => (
              <span key={key}>
                <i className={`risk-dot risk-${key}`} />
                {riskLabels[key]}
              </span>
            ))}
          </div>
        ) : (
          <div className="raw-legend" aria-label="Raw forecast variable legend">
            <strong>
              {props.frame?.variable ?? 'Wind'} · {scale.unit}
            </strong>
            <div className="raw-scale">
              {scale.stops.map((stop, index) => (
                <span className="raw-bin" key={stop}>
                  <i style={{ backgroundColor: rawPalette[index] }} />
                  {index === 3 ? `${stop}+` : `${stop}–<${scale.stops[index + 1]}`}
                </span>
              ))}
            </div>
            <p>
              Raw magnitude ·{' '}
              {props.frame
                ? clock(props.frame.requested_at, props.analysis?.inputs.origin_timezone)
                : 'not acquired'}
              {props.framePending ? ' · next frame preparing' : ''}
            </p>
            <p>Hatched cells: Unknown · saved route ranking unchanged</p>
          </div>
        )}
      </div>
      {failed && (
        <a
          className="fallback-attribution"
          href="https://www.naturalearthdata.com/about/terms-of-use/"
          target="_blank"
          rel="noopener noreferrer"
        >
          Natural Earth · public domain
        </a>
      )}
    </section>
  )
}
