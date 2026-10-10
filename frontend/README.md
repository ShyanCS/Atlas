# Spotter Atlas frontend — assessment release

## Deployment preparation

`VITE_API_BASE` accepts a same-origin local path or credential-free HTTPS `/api/v1` endpoint. Anonymous health controls the readiness/reviewer gateway; the bearer code stays in tab memory, never build variables or URLs. Dashboard/map code loads after readiness/access. Cold starts/timeouts offer manual recovery without resubmitting a trip.

Pages configuration: `wrangler.toml`, `public/_headers`, `.env.deployment.example`. Exact setup and pending authorization: root `docs/deployment/SETUP.md`. Hosted provider switches remain off. Current frontend suite: 42 cases; original sample/browser workflows are preserved. No actual Cloudflare deployment is claimed.

## Current assessment extension

Dispatch Canvas now supports explicit live geocoding, committed coordinates, IANA departure, truck profile and source-disclosed Open-Meteo/TomTom results. Keys remain in Django, never frontend environment variables. The original sample suite remains available and structurally separate. `?analysis=<UUID>` restores an unexpired saved analysis without provider calls. Live selection and clock frames never rerank the backend snapshot.

Set `ATLAS_DEV_API_TARGET=http://127.0.0.1:8001` only if Django uses an alternate local port; the default is 8000. The target must use loopback. Full setup and live source limitations are in the root README and `docs/implementation/ASSESSMENT_LIVE_REPORT.md`. No decoder, premium screen or public hosting is included.

Current offline suites: 34 frontend tests; the browser regression script still exercises authored samples. `node e2e/live-assessment.cjs` separately reads the local UUID created by the explicit live probe, requires an unexpired snapshot and makes no new provider calls or geometry screenshots. `ATLAS_FRONTEND_URL`, `ATLAS_BACKEND_URL` and `ATLAS_BROWSER_EVIDENCE_SUBDIR` document the selected local test server/evidence directory.

## Preserved foundation instructions

React/TypeScript Dispatch Canvas backed by the local Django authored sample API. This is application code, with generated API contracts and tested selection/request behavior. It does not integrate live routing, weather, geocoding, accounts, paid infrastructure, Three.js, deck.gl or a GPL decoder.

## Run locally

Use Node **24.15+ in the 24.x line** (verified runtime: 24.19.0) or a compatible 26+ runtime. TypeScript is pinned at 5.9.3 because the current lint/type-generation tools do not support the registry's TypeScript 7 release.

```sh
npm ci --ignore-scripts
npm run dev
```

Start Django separately on `http://127.0.0.1:8000`. Vite listens only on `http://127.0.0.1:5173`, with a strict port and a same-origin `/api` proxy to Django. Built preview uses `http://127.0.0.1:4173` with the same proxy. Both set DENY frame protection, nosniff and same-origin referrer headers; the HTML also specifies no-referrer. No untested CSP is claimed. The default API path is `/api/v1`; `.env.example` contains only that public path. Do not put provider keys, capabilities or database credentials into any `VITE_*` variable.

On this Windows workspace, the global npm launcher uses Node 22.12.0. Use the bundled Node executable directly with npm's CLI rather than that launcher:

```powershell
$taskNodeBin = 'C:\Users\shyan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
$env:Path = "$taskNodeBin;$env:Path"
& "$taskNodeBin\node.exe" 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run dev
```

This changes only the command process's PATH; it does not upgrade global Node. Lifecycle scripts were disabled for dependency installation. No accounts or deployments are needed for the local sample.

## Contract and state ownership

`backend/openapi.yaml` is the canonical drf-spectacular schema. Regenerate and check the committed TypeScript declarations whenever the backend contract changes:

```sh
npm run generate:api
npm run check:contracts
```

`src/contracts/types.ts` exposes the schema-derived public aliases. `src/contracts/input.ts` builds explicit sample defaults and restores an analysis's submitted input without deriving a timezone or shifting its instant. The backend resolves local time/DST ambiguity and validates decimal cargo/coordinate inputs.

`src/api/client.ts` centralizes same-origin fetch, structured API errors, safe network/cancellation messages and critical transport checks. It preserves decimal strings, including finite exponent notation; it never computes weather classifications, exposure or recommendation ranking. HTTP errors do not trigger an automatic retry or sample/live fallback. Actual/live mode is explicitly blocked by Django in this phase.

`src/state/useAnalysisWorkspace.ts` exposes:

- `state.analysis`, `selectedRouteId`, `selectedCheckpointId`, `mode`, `requestedFrame`, `displayedFrame` and `isStale`.
- `scenarios`, `loadingScenarios`, `error`, `analysisPending` and `framePending`.
- `analyze(input): Promise<Analysis | null>`, `requestFrame(hour, variable): Promise<WeatherFrame | null>`, `reloadScenarios`, `selectRoute`, `selectCheckpoint`, `setMode`, `markStale`, `discardDraft` and `clearError`.

The default mode is `arrival-risk`; `setMode` changes presentation only. The UI explicitly requests its first frame and subsequent hour/field changes. The reducer and abort controllers reject superseded requests and old-run frames. A displayed frame retains its old timestamp while another is pending. Selection is independent of the backend recommendation; selecting a checkpoint selects its route, while changing routes clears incompatible checkpoint detail. Form edits must call `markStale` even while the first request is pending, so a response cannot silently become current after an edit.

The hook owns no draft form data and scenario retries do not reset the draft or a completed analysis. Requests abort on unmount. Browser/cross-device capability persistence and production authentication remain outside this local sample implementation.

Call `discardDraft` only after explicit cancellation/reversion to the committed snapshot inputs. It restores freshness without rerouting, preserves the snapshot/selection and is a no-op while an analysis request is pending. Ordinary error dismissal does not make edited inputs current.

## Checks

```sh
npm run format:check
npm run lint
npm test
npm run check:contracts
npm run build
npm run test:browser
```

`build` includes strict TypeScript checking. Vitest/Testing Library run in jsdom with a bounded two-thread worker pool. The suites cover structured and blocked errors, exact decimal input/output, malformed payloads, explicit missing snow, selection/recommendation separation, checkpoint parent changes, draft edits during requests, cancellation, frame races, run changes and scenario recovery. They do not prove WebGL/GPU performance or full accessibility conformance; browser QA is separate. The browser script requires the local Django and Vite/preview servers and an available Chrome/Chromium executable, as documented with that suite. Installing the pinned Playwright test package does not install a browser here.

Prettier is pinned. `npm run format` formats source/configuration; generated API declarations, raw captured fixtures, public source assets and package-lock are excluded to preserve their producer formats.

## Dependencies and evidence boundary

Direct runtime dependencies: React/React DOM 19.3.0 (MIT) and MapLibre GL JS 6.13.0 (BSD-3-Clause). Vite 8.3.4, Vitest 5.0.3, Testing Library, ESLint and Prettier are development tools. TypeScript 5.9.3 is Apache-2.0. Exact resolved dependencies and available license metadata are in `package-lock.json`; pinned installation is reproducible with `npm ci --ignore-scripts`.

The package is private and `UNLICENSED` pending the application's publication-license decision. This does not change third-party notices. Natural Earth geography and bundled fonts have their own source/license records in `public/assets`, maintained with the UI assets.

Test JSON was captured only from the local authored **SAMPLE DATA** API after the final Phase 3A schema update. The mixed-eligibility unit snapshot is transparently composed from those sample scenarios and is never served as live data. No provider geometry, credentials, payment details or actual forecast observations are in the test fixtures. See `src/test/fixtures/README.md`.
