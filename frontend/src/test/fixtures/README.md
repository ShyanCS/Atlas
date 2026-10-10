# Authored sample API contract fixtures

Captured 10 October 2026 from the authorized local Django server on 127.0.0.1:8000 after its Phase 3A v2 schema/decimal/source-slot update. These are developer-authored hypothetical sample scenarios, not TomTom routes, weather-provider results or observations.

- `scenarios.json`: named sample endpoints and form defaults.
- `complete.json`, `partial.json`, `no-travel.json`: actual local API HTTP 201 response bodies for the three authored scenarios, with decimal-string inputs and 25-mile checkpoints.
- `wind-0.json`, `snow-48.json`: actual local API clock-frame responses from that complete sample analysis. The latter intentionally has missing hypothetical snow; its sample horizon is not a NOAA coverage claim.

Raw producer formatting is preserved. UUIDs/timestamps identify sample runs only; there are no access capabilities or API keys. `fixtures.ts` validates transport structure before tests consume these JSON bodies. The unit-only mixed-eligibility snapshot combines Route C from the no-travel sample with the complete sample's other candidates to verify inspection versus recommendation state; it is explicitly composed, not claimed as a separately captured API response.
