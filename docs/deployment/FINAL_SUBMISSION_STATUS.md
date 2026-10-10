# Spotter Atlas final hosted release and submission status

11 October 2026, Asia/Calcutta. Evidence records the execution host's exact UTC
timestamps. **The public example application is published and verified. Full
hosted live assessment acceptance remains BLOCKED; sample success is not live success.**

## Published application

- Application: https://spotter-atlas-assessment.pages.dev/
- API health: https://spotter-atlas-assessment-api.onrender.com/api/v1/health/
- Repository: https://github.com/ShyanCS/Atlas
- Release PR: https://github.com/ShyanCS/Atlas/pull/1
- Initial verified runtime source: `8a029ca912cdafa1664641cae68db919f322f200`.
- Initial Render deployment: `dep-db59bt2jnfac739m80pg`; persistence redeployment:
  `dep-db59dh7avr4c73ftnqfg`.
- Initial Pages production deployment: `201066c5-7d61-41f5-97c1-6fb976b84e90`.

Dispatch Canvas opens without a login screen. One Example trip indicator and
expandable sources identify illustrative data. Three fixed scenarios share
server-owned snapshots; private/live records and arbitrary POSTs are protected.
The planner preserves drafts on rejection. Contextual planning authorization is
available only after an operation is denied, keeps access in tab memory, sends
no request when set, and does not turn providers on. No premium product feature,
risk-policy change or provider-adapter replacement was introduced.

## Observed verification

| Check | Result and evidence |
|---|---|
| Local PostgreSQL regression | PASS: 297 tests, no skips, 17.72 seconds; disposable PostgreSQL 16.2 |
| Initial frontend regression | PASS: 46 tests; lint, formatting, contracts, TypeScript and Vite build |
| Final frontend regression | PASS: 48 tests, 16.94 seconds, including contextual tab-only authorization; lint/format/typecheck/build/contracts pass |
| Local browser regressions | PASS: 13 existing groups + 12 direct-entry groups; all 147 frame responses |
| GitHub CI, initial release | PASS: https://github.com/ShyanCS/Atlas/actions/runs/38080957297 — all three required jobs |
| GitHub CI, final application | PASS: https://github.com/ShyanCS/Atlas/actions/runs/38082001616 — 297 backend/48 frontend cases and browser regression |
| Hosted API | PASS: 161 HTTP requests; complete/partial/No Travel scenarios; all 147 frames; protected operations/private records |
| HTTPS and CORS | PASS: HTTPS, exact Pages origin, attacker origin rejected, security headers and CSP |
| Actual hosted browser | PASS: 12 groups, desktop 1440×900/mobile 390×844, MapLibre, route selection, keyboard 0/48 forecast positions, draft retention, contextual private authorization and reload without a creation POST |
| PostgreSQL | PASS: 16.15, verified TLS, `verify-full`, required channel binding, migration 0004 applied |
| Restart persistence | PASS: published public/private result representations unchanged via HTTP and direct SQL after redeployment; existing isolated cap debit remains 1 |
| Provider counts | Unchanged: routing 0, geocoding 0, weather 0; no budget reset |
| Secret scans | PASS: 75 initial staged review files/14 built files, zero known secrets or forbidden private paths; subsequent release files rescanned |

[Hosted evidence and screenshots](evidence/2026-10-11/README.md).
The final contextual-access follow-up and publication revisions are recorded
in `evidence/2026-10-11/final-publication.json` after their verification.

Hosted frame batch: **61.922 seconds** for 147 reads. Mean API round trip across
the 161-request batch: **0.473 seconds**, maximum **3.186 seconds**. Desktop and
mobile entry checks took **5.363/2.152 seconds**, including header/map/UI checks;
these are not precise isolated time-to-interactive measurements. Sampled Render
memory peaked at **110,649,340 bytes (~105.5 MiB)** of **536,870,900 bytes (~512 MiB)**;
sampled CPU peaked at **0.0669** against the reported **0.15** limit. Samples do
not certify live worst-case memory. Actual idle-spin-down cold start, physical GPU,
screen-reader and real mobile-device certification remain unmeasured.

One overloaded local follow-up Vitest run timed out starting two workers (42 tests
completed, two worker errors); it was not accepted as a pass. A fresh complete run
passed all 48 tests without unhandled errors. Local browser verification and CI
are rerun on the final source rather than relying on that incomplete run.

## Infrastructure and release controls

Existing infrastructure was reused; no new project or billing change:

- **Cloudflare Pages:** static-only Free deployment, root `frontend`, output `dist`,
  Node **24.19.0** confirmed in actual build logs, explicit HTTPS API build setting.
  Production auto-deployment stays disabled; previews stay disabled.
- **Render:** existing Python Free service in Virginia, one instance, existing
  Gunicorn configuration and scripts. Migrations and budget initialization execute
  at startup. Auto-deployment stays off. Platform health remains TCP because the
  integration lacks the HTTP-health-path setting; independent HTTP/DB checks pass.
- **Neon:** existing standalone Free (`free_v3`) `spotter-atlas-db`, PostgreSQL 16,
  `aws-us-east-1`, pooled connection, fixed 0.25 CU, 512 MiB storage ceiling and
  six-hour restore history. No Neon Auth or alternate ORM was added.
- Public examples flag is 1; all live/public-provider permission flags stay **0**.
  The existing private access hash and Django secret remain server-only. No TomTom
  key was installed. No provider request, paid plan, purchase or terms acceptance
  occurred. Infrastructure payment/overage confirmations supplied earlier are
  preserved; account-specific provider allowances are not invented.

An unrelated pre-existing `Workers Builds: atlas` integration fails. It is separate
from the working Pages project and the three required GitHub Actions checks. No
Worker configuration, paid feature or unrelated repository association was changed.

## Mandatory assessment acceptance

| Requirement | Hosted status |
|---|---|
| Origin/destination, departure, cargo and truck profile | Form implemented; real search/submission BLOCKED by hosted provider activation |
| Three genuine compatible truck routes | BLOCKED on host; existing local TomTom workflow preserved, illustrative examples are not evidence |
| 10/25/50-mile checkpoints, interpolated arrival times | Domain/tests PASS; hosted live input/route verification BLOCKED |
| ETA weather and exact risk/load rules | Domain/tests PASS; hosted real provider verification BLOCKED |
| Severe/High/average/time ranking and eligibility | PASS for tested authored scenarios; hosted live acceptance BLOCKED |
| Interactive route/checkpoint map | PASS for hosted examples; real geometry display gate remains unresolved |
| Corridor weather heatmap and 0–48 slider | PASS for all example frames; hosted source-grounded live frames BLOCKED |
| GitHub + hosted application | Published; current release evidence and professional README supplied |
| 5–10 minute Loom walkthrough | NOT RECORDED; [recording script](SUBMISSION_WALKTHROUGH.md) supplied |

## Specific remaining actions

1. **Provider release confirmation:** the earlier personal noncommercial scope and
   approximate provider snowfall approval are preserved, but they did not establish
   hosted public acquisition, TomTom display/limited retention or account zero-charge
   controls. The account owner handles these matters. No agreement upload or renewed
   broad research is requested. Until permitted hosting and finite zero-charge
   controls are confirmed, live flags remain off and no credential is installed.
2. **After confirmation:** securely install the authorized existing TomTom key,
   retain private planning access and durable caps (8 routing/12 geocoding/64 weather
   attempts), enable only the confirmed release flags, and perform one bounded
   Dallas–Houston end-to-end frontend run. Verify distinct routes, ETA/coverage,
   exact exposure/ranking and all live frames; report shortfalls rather than fake
   weather or substitute examples. No provider search or native decoder is needed.
3. **Submission video:** record/upload a 5–10 minute Loom walkthrough and include
   its URL. Record the complete live flow only after step 2 passes; a labeled sample
   preview alone does not satisfy the original assignment's live-functionality goal.

The original assessment's **16 work hours/four days** limit, React/Django
requirements, thresholds and ranking order remain authoritative. This longer
engineering history is not represented as a timed assessment completion.
