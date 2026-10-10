# Spotter Atlas walkthrough and submission

Use https://spotter-atlas-assessment.pages.dev/ and https://github.com/ShyanCS/Atlas.
Do not describe the public example as a genuine provider route analysis. The current
hosted live permission gate must pass before recording a complete assessment demonstration.
Never show secrets, service environment pages, authorization headers or private account files.

## Suggested 7–9 minute recording

1. **0:00–0:45 — Product.** Explain weather-aware truck-route comparison; open Dispatch
   Canvas, identify the example trip and show desktop/mobile composition.
2. **0:45–2:15 — Real planning, when enabled.** Search/commit Dallas and Houston,
   confirm timezone, future departure, cargo versus total truck weight, truck dimensions
   and 10/25/50-mile spacing. Submit exactly once; explain provider waiting and errors.
3. **2:15–3:45 — Routing and checkpoints.** Show three distinct compatible truck
   candidates, checkpoint numbering, cumulative ETA and wind/rain/snow at arrival.
   Fewer alternatives or incomplete weather must be disclosed, never hidden.
4. **3:45–4:45 — Recommendation.** Explain eligibility first, then Severe miles,
   High miles, distance-weighted average risk and travel time. Route selection inspects
   the result; it never changes backend ranking. Show No Travel and Unknown behavior.
5. **4:45–6:00 — Corridor forecast.** Change raw variable and move through 0–48 hours;
   distinguish raw spatial conditions from arrival-time route-risk segments. Explain
   source timestamps, approximate provider snowfall and unavailable cells.
6. **6:00–7:00 — Mobile and resilience.** Show inspector/driver briefing, keyboard
   controls, warnings, sources and map attribution. Explain free-host wake-up behavior.
7. **7:00–8:30 — Engineering.** Briefly show README, pure domain tests, typed API,
   immutable PostgreSQL snapshots, durable finite request budgets and CI. Do not show
   provider geometry in Git, database credentials or account administration screens.

## Final human deliverable

Record and upload a 5–10 minute Loom walkthrough and place its share URL in the final
submission alongside the application and repository links. No recording/upload has
been performed by this checklist. If hosted live use is blocked, report that limitation
and record only an accurately labeled preview; it is not full assessment completion.
