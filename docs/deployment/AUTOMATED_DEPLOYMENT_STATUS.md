# Automated assessment deployment — verified Demo Mode release

10 October 2026. **Neon, Render and Pages are provisioned; hosted Demo Mode verification passed. Hosted live providers remain disabled.**

## Services and approvals

| Service                 | Status | Actual configuration                                                                                                                                       |
| ----------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Neon `spotter-atlas-db` | PASS   | Free organization; `shiny-rain-69323500`; AWS US East 1 (Virginia); PostgreSQL 16.15; fixed 0.25 CU; transaction pooling                                   |
| Render backend          | PASS   | Free Python service in Virginia; reviewer-protected; automatic deployments off; [health](https://spotter-atlas-assessment-api.onrender.com/api/v1/health/) |
| Cloudflare Pages        | PASS   | Static Git-integrated [Dispatch Canvas](https://spotter-atlas-assessment.pages.dev); automatic production/preview deployments off                          |

The user separately approved backend and frontend publication and confirmed no payment method or chargeable overages in the Render workspace. No paid plans, upgrades, billing activation, paid fallbacks, Functions, Neon Auth, new ORM or hosted provider calls were introduced.

Repository: <https://github.com/ShyanCS/Atlas>, branch `refine/product-identity`. Render runs `4ba439a`; Pages runs `adeba19465414a4335c3ff13ea2d09d4cd8688e2`. The latter adds only root/frontend Node-version pins. Application code is identical between these revisions. `main` remains unmerged and PR #1 remains open.

## Database and security

- Connection information was obtained without displaying credentials. Local DB/reviewer credentials use Windows user-bound encryption. Wrangler OAuth uses an encrypted file with its key in Windows Credential Manager. No plaintext credential file was created or committed.
- Existing Django migrations applied over the direct endpoint with `verify-full` certificate/hostname verification and required channel binding. Verification used the pooled endpoint. Actual Neon immutable-result triggers, snapshots and durable request caps passed.
- Default libpq CA lookup failed on Windows and Render. Local verification exported existing trusted Windows roots; Render uses `/etc/ssl/certs/ca-certificates.crt` explicitly. Certificate/hostname checks were preserved. The deployment example records the corrected Linux URL parameter.
- Selected Neon API limits: **512 MiB logical storage / six-hour restore history**. Changing suspension and requesting 24-hour history were rejected; restrictions were not bypassed or upgraded. Compute was observed idle/suspended at 17:56:01 UTC, pooling enabled.
- Anonymous health, reviewer access, invalid-code rejection, HTTPS/security headers, preflight and rejected foreign origins passed. Actual browser requests from `https://spotter-atlas-assessment.pages.dev` to Render passed exact CORS.
- All three live/public-provider flags remain **0**. No TomTom key was installed on Render. Hosted live submission returns `LIVE_MODE_UNAVAILABLE`; health reports `live_available=false`.
- Production counters remain **routing 0 / geocoding 0 / weather 0**, caps **8 / 12 / 64**. Cap verification used a separate isolated ledger, with no I/O or production-counter reset. The final count was 11 current sample snapshots. Existing 20-snapshot admission and one-hour expiry remain in place.

## Fresh checks and measurements

| Check                                    | Observed result                                                                                                                                                       |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Local backend suite                      | 271 passed; two PostgreSQL-only cases skipped                                                                                                                         |
| Fresh GitHub PostgreSQL suite            | 273 passed in 8.66 seconds                                                                                                                                            |
| Frontend suite                           | 44 passed                                                                                                                                                             |
| TypeScript/build and generated contracts | PASS                                                                                                                                                                  |
| Required GitHub CI                       | Backend, Frontend and Browser smoke PASS; Pages PASS                                                                                                                  |
| Actual hosted scenarios                  | Complete → recommended; partial → unverified; No Travel → blocked                                                                                                     |
| Actual hosted forecast frames            | All 147 variable/hour combinations covering 49 positions PASS                                                                                                         |
| Backend redeployment                     | Analysis unchanged; durable counters/initializer persistence PASS                                                                                                     |
| Hosted Chrome                            | Seven check groups PASS; 1440×900 and 390×844; no page errors, unexpected external requests or provider calls                                                         |
| Browser interactions                     | Reviewer unlock/relock; MapLibre; mobile chooser; selection preserves recommendation; keyboard 0/48 slider; Unknown snowfall; driver briefing; no horizontal overflow |
| Built-asset credential scan              | 14 files, zero known credential matches; largest asset 1,095,935 bytes                                                                                                |

Hosted POST timings: complete **2.895 s**, partial **2.549 s**, No Travel **2.197 s**. The 147 frame reads took **61.758 s**; mean round-trip time across the 157-request batch was **0.460 s**. Post-redeployment health: **0.406 s**. Hosted sample-to-map: **5.316 s desktop / 4.283 s mobile**.

Direct Neon checks from this machine took **6.606 s** for the sample POST and **423.702 s** for 147 frame reads; these are client/network-specific, not Render timings. Render sampled memory peaked at **111,099,900 bytes (~106 MiB)** against its reported **536,870,900-byte (~512 MiB)** limit; reported CPU limit was **0.15**. Samples do not certify worst-case live memory. Same-code redeployment reached live status in approximately **69 s**.

Loading feedback was tested by delaying acquisition of a real hosted health response by 6.5 seconds. **Actual Render idle-spin-down cold-start time was not measured.** Chrome used SwiftShader; physical GPUs and real devices were not certified.

[Evidence and screenshots](evidence/2026-10-10/): settled screenshots restore an existing analysis without new submissions. Initial-loading images and the failed mobile harness attempt remain separately retained.

## Pages configuration and resolved failures

Root `frontend`; output `dist`; Node **24.19.0**; source branch `refine/product-identity`. Final command:

```sh
VITE_API_BASE=https://spotter-atlas-assessment-api.onrender.com/api/v1 npm run build
```

The first two builds stored the correct variables in the Pages API but did not use them during build: logs showed Node 22.16.0 and the browser called Pages' own `/api/v1/health/`. Root/frontend `.node-version` pins plus the explicit public API assignment resolved this. Final logs confirm installing/using Node 24.19.0, and real browser traffic calls Render. Both project variables remain configured. If the backend URL changes, update the variable and command. No secret belongs in the command or `VITE_*` values.

Other resolved observations: Vercel-managed Neon creation was blocked until standalone Free access was available; Cloudflare Git installation returned HTTP 401 until the user connected GitHub; one bounded read-only follow-up resolved a transient Cloudflare HTTP 503. Local pytest initially had 15 sandbox temporary-directory setup errors; a checked fresh workspace directory yielded 271 passes. The browser harness initially selected a hidden desktop card on mobile; using the existing mobile chooser fixed verification without changing the UI.

## Remaining actions and limits

1. **Reviewer access:** on this same Windows account, run the helper below, then paste the private code into the published access screen. It copies without printing. Share only privately with authorized reviewers; never put it in URLs, Git, frontend variables or reports.

   ```powershell
   & .\backend\.local\deployment\copy-reviewer-code.ps1
   ```

2. **Hosted live analysis:** intentionally NOT ENABLED or verified. Requires separate public weather-use/TomTom display-release confirmations and explicit activation authorization. No agreement documents are requested; the earlier local live milestone is not a hosted live pass.
3. **Repository review:** the user authorized synchronizing the README, nonsecret CA/region/cache-ignore corrections, hosted evidence and PR description on 11 October 2026. This update changes documentation/configuration only; it does not republish services, merge main or enable live providers. Deployed revisions above remain the actual tested release; the synchronization commit is a later source revision. Main remains subject to PR review.
4. **Separate Worker:** `Workers Builds: atlas` fails. Its Worker was not provisioned or modified by this workflow. Review that separate build association if desired; it does not prevent the successful Pages deployment or the three required CI checks.
5. **Render integration difference:** root/HTTP-health-path fields are unavailable in the integration. Commands use `cd backend` plus the existing scripts, and platform health defaults to TCP. The intended HTTP endpoint passed independent checks. Its dashboard can optionally set `/api/v1/health/` as the platform health path.
6. Real idle cold-start timing, real-device/GPU checks and the employer walkthrough remain follow-up verification. Premium features and an architecture overhaul are unnecessary for this sample deployment.

Free quotas are finite, including Render's shared workspace allowances. No keep-alive pinger, automatic provider retry, upgrade or paid fallback was added. This report verifies a **hosted sample release**, not production readiness or assessment completion with hosted live data.
