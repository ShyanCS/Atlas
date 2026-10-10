# Spotter Atlas local API contract v1

## Hosted assessment preparation

`health/` additionally returns `assessment_access_required`. Hosted API paths require a private reviewer Bearer code except health/preflight; local defaults retain anonymous samples. OpenAPI describes conditional access without embedding a secret. Structured 401/429/503 responses preserve the error envelope; no automatic provider retry is introduced.

Hosted mode requires PostgreSQL. A database trigger protects published result/frame JSON; provider budgets persist independently; selected hourly frames are projected in SQL. Sample/live risk and frame contracts are unchanged. Hosted live additionally requires public-weather/public-routing confirmation switches. Sample operation requires no provider credentials. See the deployment readiness report and setup checklist before publishing.

## Current local assessment extension — 10 October 2026

The API now supports explicit `mode=live` in addition to preserved sample scenarios. OpenAPI in `openapi.yaml` and generated frontend declarations describe both modes. No native decoder, public deployment or production authentication has been added.

- `POST locations/geocode/` with `{ "text": "Dallas Texas" }` returns named coordinate candidates, optional timezone and entry points. Selection is committed explicitly. Geocoding does not establish truck-access legality or invent a timezone; callers provide an IANA zone.
- `POST analyses/` accepts `mode=live` with arbitrary committed stops, existing departure/cargo/interval fields, and optional `truck_profile`: `current_weight_kg`, `height_m`, `width_m`, `length_m`, `axle_weight_kg`, `axle_count`. Physical weight is separate from `load_weight_lb`. Whole-second departure precision is required. Departure must fall within now through 48 hours, with five-minute form grace; route duration is capped at 48 hours and 160 unique checkpoint locations. No sample fallback occurs.
- Live availability requires `ATLAS_LIVE_ENABLED`, `ATLAS_NONCOMMERCIAL_ASSESSMENT`, `ATLAS_ACCEPT_PROVIDER_SNOWFALL` and a server-side `TOMTOM_API_KEY`. Health exposes only availability, not credentials. Missing authorization/configuration returns `LIVE_MODE_UNAVAILABLE`.
- Live weather uses Open-Meteo ICON Global JSON: 10 m wind, liquid `rain + showers`, provider snowfall with the disclosed fixed 7:1 relationship. Nullable model initialization, requested/source coordinates, retrieval time, matched valid instant/interval and source-policy flags remain explicit. Missing either rain component makes rain Unknown. Physical native intervals are not established by hourly service timestamps.
- `GET analyses/{uuid}/` and the unchanged frame endpoint read immutable saved results. Live frames cover 0–48 hours and wind/rain/snow from acquired scalar series; no provider I/O occurs on reads. `mode=live`, `sample_data=false`, forecast provenance and provider routing eligibility distinguish them structurally from sample results.
- One-hour live snapshot expiry and finite local provider attempt budgets apply. Snapshot creation is synchronous, with one admitted live analysis and one provider HTTP request at a time. Client cancellation does not promise cancellation of already-started server acquisition. No retry, paid fallback or synthetic substitution is performed.
- Typed errors include `LIVE_MODE_UNAVAILABLE`, `FORECAST_DEPARTURE_WINDOW`, `LIVE_DEPARTURE_PRECISION`, `LIVE_ANALYSIS_BUSY`, `ASSESSMENT_REQUEST_CAP`, provider quota/transport errors, `NO_TIMED_UNIQUE_ROUTES`, `CHECKPOINT_ACQUISITION_LIMIT` and weather contract errors. Responses/logs never export upstream credential-bearing URLs or raw payloads.

See [public source readiness](../docs/deployment/READINESS.md). The following original sample contract remains applicable to sample mode; its historical limitations do not describe the new opt-in live path.

## Preserved Phase 3A sample contract

Base URL: `http://127.0.0.1:8000/api/v1/`. The API uses snake_case JSON, UTC instants, IANA local-time resolution, GeoJSON coordinates in longitude/latitude order, and Decimal strings for weather/distance/mean/coverage values. Frontend formatting may round for display; frontend code must not compute risk, exposure or recommendations.

## Operations

| Method/path | Result |
|---|---|
| `GET health/` | Process health, sample mode, `live_available=false`; no provider request |
| `GET scenarios/` | Named committed endpoints, default input and complete/partial/no-travel scenarios |
| `POST analyses/` | Validates sample input, calculates synchronously and returns the completed immutable snapshot with HTTP 201 |
| `GET analyses/{uuid}/` | Reads the saved completed snapshot |
| `GET analyses/{uuid}/frames/?hour=0&variable=wind` | Separate raw-variable synthetic clock frame; hour is an integer 0–48, variable wind/rain/snow |
| `GET schema/` | drf-spectacular OpenAPI; generated checked-in schema is `backend/openapi.yaml` |
| `GET docs/` | JSON documentation pointers; no external Swagger/CDN assets |

POST is deliberately synchronous. Queued/running/complete timestamps are actual lifecycle audit entries, not a worker queue, resumable job, phase polling or a promise of independent processing after a client leaves.

## Input and temporal rules

```json
{
  "mode": "sample",
  "scenario": "complete",
  "origin": {"name": "Chicago, IL", "latitude": "41.8781", "longitude": "-87.6298"},
  "destination": {"name": "Atlanta, GA", "latitude": "33.7490", "longitude": "-84.3880"},
  "departure_local": "2026-10-10T06:00:00",
  "origin_timezone": "America/Chicago",
  "load_weight_lb": "24000",
  "checkpoint_interval_miles": 25
}
```

`departure_at` with an explicit offset may replace `departure_local`. At least one is required; both must describe the same instant if both are supplied. `departure_local` must be a wall time without an offset. DST folds require explicit `departure_fold=0` (first occurrence) or `1` (second); omission/null raises `DEPARTURE_TIME_AMBIGUOUS` when ambiguous. Nonexistent local times raise `DEPARTURE_TIME_NONEXISTENT`. The backend domain resolves time; no custom frontend timezone conversion is needed.

Responses always normalize `inputs.departure_local` for the selected IANA zone, even for UTC-only requests; `inputs.departure_fold` is 0/1 for an actual ambiguous occurrence and null otherwise. The scenarios endpoint also supplies local time/fold defaults. Forms should initialize/edit those returned values, and clear a prior explicit fold when the user changes the date/time or zone.

These illustrative samples allow historical or future absolute departures; no live forecast-horizon availability is implied. The IANA field supplies the user-selected display/entry zone and is not returned by geocoding. Named sample endpoint objects are the only accepted stops; arbitrary labels or mismatched coordinates return `SAMPLE_LOCATION_UNAVAILABLE`. There is no invented typeahead/geocoding result.

Sample datetime arithmetic must remain representable: the six-hour model-run lookback and the 48-hour clock plus two-hour source-slot padding require UTC departure between `0001-01-01T06:00:00Z` and `9999-12-29T21:59:59.999999Z`, inclusive. UTC offset normalization and the selected IANA local-time round trip must also fit Python's years 1–9999. Values that overflow any of those operations return **400 `DEPARTURE_TIME_UNSUPPORTED` before a snapshot is created**. These arithmetic bounds describe authored samples; they do not assert provider availability, a live forecast horizon or historical weather coverage.

Cargo input is nonnegative, at most 200,000lb, and accepts two decimal places. It remains cargo weight, distinct from total vehicle weight. Intervals are exactly 10/25/50 miles. Unknown fields, invalid modes, nonfinite values and repeated frame query parameters are rejected. Request bodies are capped at 16KiB.

Requests with `mode=live` or `actual` return **503 `LIVE_MODE_UNAVAILABLE`** before creating a record. There is no provider callback or paid fallback.

## Authoritative analysis output

`Analysis` includes its UUID, complete status, mode/sample flag, scenario, policy/fixture versions, UTC lifecycle/expiry, normalized inputs, three routes, backend recommendation and explicit warnings. Route IDs are `route-a`, `route-b`, `route-c` and are scoped to the analysis.

Routes contain original illustrative GeoJSON lines, synthetic cumulative timing, distance/duration/arrival, exact domain exposure strings, distance-weighted mean, complete fraction, eligibility/reasons, eligible rank (null when disqualified), checkpoints and individually sliced risk-span geometry. `routing_eligibility_basis=authored_sample_assumption` means fixture validation, not verified truck legality. Sample distances/durations are source inputs; all risk and ranking values are computed by `atlas.domain`.

Checkpoint IDs such as `route-b-cp-12` are stable within the analysis. Index 0 is Start, interior index n is CPn, and the last is Finish. Each contains chainage, interpolated UTC ETA, coordinate, canonical overall risk, completeness, governing conditions, known lower bound, rule IDs and backend-generated `rule_explanations`. Risk values are `low`, `moderate`, `high`, `severe`, `no_travel`, `unknown`.

Each wind/rain/snow measurement is `{value, unit, missing_reason, provenance}`. Values are exact Decimal strings or null. Units are mph/in/hour. Provenance is explicitly synthetic: authored source/model, illustrative model run, selected valid instant, rain/snow one-hour start/end interval, actual local generation/retrieval timestamp and sample flags. Snow is hypothetical native-depth semantics, not NOAA data or a SWE conversion.

The sample adapter creates explicit native hourly instantaneous/accumulation slots, then invokes domain matchers. Risk classification uses the same selected values as provenance. Missing native depth remains null/Unknown; values at arbitrary ETA minutes are not relabeled as another forecast hour.

Recommendation is `{route_id, state, reason, ranking_criteria}` with state recommended/blocked/unverified. The ID is assigned only by the backend's eligibility-first exact assessment sequence: Severe miles, High miles, weighted mean, duration. No Travel or incomplete required weather prevents recommendation; no least-unsafe route is labeled qualified.

## Frame output and immutability

`Frame` identifies analysis, hour, variable, exact requested clock, unit, `classification_basis=selected_variable`, acquisition status ready/partial/missing, coverage counts/reasons, synthetic cells and warnings. This basis scopes the raw displayed metric; **frames contain no overall safety classification or recommendation**. Numeric weather legends are separate from ETA risk legends.

Cell geometry is an original illustrative regular polygon, not a model-native grid. Its measurement retains the same synthetic per-variable provenance contract. The complete scenario has known hypothetical snow through the illustrative 24-hour source window; the partial scenario ends that depth window at six hours. Native bucket availability controls coverage, so a departure with minutes can lose the last containing interval. Beyond coverage, snow value is null with an explicit missing reason.

All 49 × 32 cell slots and their source values/times are frozen in the local snapshot during creation; frame reads format those stored slots. They never mutate route recommendation, measurements, ranking, or exposure. Refresh creates a new analysis. Preliminary v1 fixtures remain preserved but return `ANALYSIS_VERSION_UNAVAILABLE` after the source-slot contract moved to v2; they are not silently rescored.

## Errors, limits and local security boundary

```json
{"error":{"code":"LIVE_MODE_UNAVAILABLE","message":"Live providers are unavailable in this sample-only local foundation.","details":{}},"request_id":"a UUID"}
```

Every response includes `X-Request-ID`; a valid supplied UUID is retained, otherwise a new one is generated. Logs include only event/request ID/method/status/duration, without bodies, locations, credentials or query strings. Unexpected failures return a generic `INTERNAL_ERROR`, not a stack trace.

Relevant errors: VALIDATION_ERROR (400), SAMPLE_LOCATION_UNAVAILABLE (400), DEPARTURE_TIME_AMBIGUOUS/NONEXISTENT/INCONSISTENT/UNSUPPORTED (400), ANALYSIS_NOT_FOUND (404), ANALYSIS_NOT_READY/VERSION_UNAVAILABLE (409), ANALYSIS_EXPIRED (410), REQUEST_TOO_LARGE (413), SAMPLE_ADMISSION_LIMIT (429), LIVE_MODE_UNAVAILABLE (503).

SQLite persistence is local-only. Default retention is 24 hours, with a 100-record admission ceiling. Expired records are removed when a new analysis is admitted, not by a background scheduler. Admission serialization is limited to this single local process, not a distributed or multi-tenant quota guarantee. UUIDs are identifiers, not authorization capabilities. There is no private-trip security claim or approval to expose this anonymous development server publicly.

DEBUG defaults false; allowed hosts and CORS origins are explicit local values; no credentialed CORS or cookies are used. The random fallback secret is per-process and only suitable for this unused-session local mode; deployment requires separately reviewed settings and a stable injected secret.

Schema generation:

```powershell
cd backend
& .venv/Scripts/python.exe manage.py spectacular --file openapi.yaml --validate --fail-on-warn
```

Frontend types should be generated from this schema. Important components: Analysis, AnalysisInputRequest, Route, Checkpoint, Measurement, Provenance, Frame, FrameCoverage, LineGeometry, PolygonGeometry, Scenarios, ErrorResponse.
