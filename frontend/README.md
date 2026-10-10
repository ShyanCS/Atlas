# Spotter Atlas frontend

React/TypeScript presents the **Dispatch Canvas** in the **Atlas Noir** visual identity. Django supplies authoritative analysis results; the frontend owns inspection, draft state, forecast controls and responsive presentation.

## Run

Use Node 24.15+ in the 24.x line (verified 24.19.0). From `frontend/`:

```sh
npm ci --ignore-scripts
npm run dev
```

Start Django separately on `http://127.0.0.1:8000`. Open `http://127.0.0.1:5173` and choose **Explore Demo**. Demo Mode exposes complete, Unknown-coverage and No Travel scenarios without provider credentials.

For an alternate local backend, set `ATLAS_DEV_API_TARGET=http://127.0.0.1:8001` before Vite. The development proxy accepts loopback only. A hosted build uses a credential-free HTTPS `VITE_API_BASE` ending in `/api/v1`; see [.env.deployment.example](.env.deployment.example).

On this Windows workstation, use the bundled Node runtime if the global Node 22 launcher is selected:

```powershell
$taskNodeBin = 'C:\Users\shyan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
$env:Path = "$taskNodeBin;$env:Path"
npm run dev
```

## State and contracts

- `src/contracts/`: schema-derived types and submitted-input helpers; regenerate with `npm run generate:api` when OpenAPI changes.
- `src/api/`: HTTPS/same-origin transport, typed errors and structural validation. Demo/Live labels reflect backend data modes; null values remain Unknown.
- `src/state/`: one analysis identity, route/checkpoint selection, stale drafts, cancellation and frame-race protection. Inspection and forecast scrubbing cannot rerank the saved result.
- `src/components/`: dashboard, planning form, route cards, inspector, timeline, access gateway and MapLibre map with accessible fallback.
- `src/styles/atlas.css`: Atlas Noir tokens, responsive composition and reduced-motion behavior.

The private reviewer code stays in tab memory. Readiness, cold starts and timeouts provide manual recovery without automatically resubmitting a trip. Dashboard/map code loads after readiness/access.

## Check

```sh
npm run lint
npm run format:check
npm run check:contracts
npm test
npm run build
```

With local servers and Google Chrome available:

```sh
npm run test:browser
```

The browser suite exercises demo scenarios. Its JSON fixtures contain illustrative data, not provider responses. [Browser guide](e2e/README.md) · [Fixture provenance](src/test/fixtures/README.md)

## Sources and configuration

Live Analysis retains provider attribution, timestamps, missing-data reasons and the approximate snowfall disclosure. Current Open-Meteo Free access has a noncommercial scope; hosted public live use remains controlled by backend release switches. No secrets belong in frontend build variables.

[Product overview](../README.md) · [API contract](../backend/API_CONTRACT.md) · [Deployment](../docs/deployment/SETUP.md) · [Security](../SECURITY.md)
