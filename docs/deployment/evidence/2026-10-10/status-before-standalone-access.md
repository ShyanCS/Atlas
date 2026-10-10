# Automated assessment deployment status

10 October 2026. Infrastructure setup authorized; frontend publication and hosted live-provider activation require separate approval.

## Phase A — Neon

Authentication: **PASS** after connecting the Neon integration.

The authenticated inventory exposes one Free organization managed by Vercel and one existing Singapore project. Its main branch is archived and its endpoint has pooling disabled. Neither was modified.

Creating `spotter-atlas-db` through the Neon API returned **HTTP 404: action restricted; organization is managed by Vercel**. No new project was created. This is an account-management restriction, not a Django failure.

**BLOCKED:** select/create a standalone Neon Free organization and make it accessible to the existing integration. No payment method, plan upgrade or account secret is requested. After access is available, create a dedicated project in `aws-us-east-1`, paired with Render Virginia, using PostgreSQL 16, fixed 0.25 CU compute and 300-second idle suspension. Confirm the selected organization's Free plan before creation.

Pooled connection retrieval, certificate-verified TLS, migrations, immutable snapshots and durable budgets on actual Neon: **NOT RUN**. No database password or connection string was retrieved or exported.

## Phases B and C

Render: **NOT PROVISIONED**, pending Phase A. A Render integration is available but was not authenticated in this session. Existing `render.yaml` selects Free compute and disables automatic deployment. Build/start scripts, reviewer hash, PostgreSQL configuration and exact host/CORS requirements are present.

Cloudflare Pages: **NOT PROVISIONED**, pending the backend URL and frontend-publication approval. No Cloudflare CLI or process/user API credential was available. Planned configuration remains root `frontend`, build `npm run build`, output `dist`, Node `24.19.0`, and HTTPS `VITE_API_BASE` ending in `/api/v1`.

`ATLAS_LIVE_ENABLED`, `ATLAS_PUBLIC_TOMTOM_CONFIRMED` and `ATLAS_PUBLIC_WEATHER_CONFIRMED` remain disabled. No provider key is needed for Demo Mode.

## Source revision and preflight

Repository: <https://github.com/ShyanCS/Atlas>. Main remains `5743e379b8f3ef00b4911148593cd0b57c83fe7a`. The reviewed product-copy revision `4ba439a` is available on `refine/product-identity` in PR #1; the PR is open and all three required checks passed. No merge was performed.

Fresh local deployment-focused verification in this setup session:

- Backend release/security tests: **20 passed, 2 PostgreSQL-only cases skipped** on SQLite. This does not validate Neon.
- Frontend endpoint/reviewer gateway tests: **8 passed**.
- Generated API contract consistency: **PASS**.

No production code, policy, adapters or dependencies changed during this preflight. Earlier CI results remain historical evidence, not hosted acceptance.

## Hosted acceptance still pending

No hosted URLs, TLS/CORS measurements, restart-persistence tests, browser screenshots, cold-start timings, service memory measurements or hosted live analyses exist for this setup attempt. Perform these only after the relevant service is provisioned and publication is approved.

No accounts were created, paid features selected, payment methods added, billing enabled, frontend published or hosted provider calls made. Existing account payment-method status was not verified and must not be inferred from the Free plan label. Render account controls must prevent paid bandwidth/build overages before publishing its service.
