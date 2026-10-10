# ₹0 assessment publishing checklist

This is prepared configuration. **No accounts, repository publication or deployment are authorized by this checklist.** Repository: https://github.com/ShyanCS/Atlas. Hosting project URLs remain blank. Existing personal noncommercial permission does not automatically enable public hosted weather use.

## Before publishing

1. Obtain the user's explicit deployment/repository authorization and select the repository and three projects. Share repository access with the employer as required; public visibility is not assumed.
2. Confirm the intended hosted assessment's Open-Meteo use is permitted, and the user's TomTom public-use/display release check is complete. No account agreements or private keys need to be uploaded to this workspace. Keep both public permission switches **0** until those checks are confirmed.
3. Use only Free plans. Do not attach payment methods, enable automatic paid overages, upgrade plans or accept a paid substitute. If a setup flow requires a paid commitment, stop. Confirm actual account quotas in each dashboard; source preparation does not verify an account's billing configuration.
4. Review the clean release source/package and its scan manifest. Never push `.env` files, SQLite databases, provider ledgers/caches, private geometry, `.venv`, `node_modules`, extracted PostgreSQL tools or historical ZIP packages.

## Neon Free — database

- Create one Free project/database in a region near the selected Render service. Preserve scale-to-zero, keep compute small and monitor usage. Do not enable paid add-ons.
- Copy the **pooled** connection string to Render's private `DATABASE_URL`. Use `sslmode=verify-full&sslrootcert=system&channel_binding=require`; percent-encode credentials. The application disables prepared statements/server-side cursors and closes request connections for transaction-pool compatibility.
- The current official [Free plan](https://neon.com/docs/introduction/plans) documents 100 CU-hours/project/month, 1 GB Postgres storage/project and 5 GB network transfer/project. [Pricing](https://neon.com/pricing) states no credit card is required and idle compute suspends. Check the actual selected account plan before proceeding.
- Migrations create short-lived snapshots, a finite attempt ledger, request-window rows and a PostgreSQL trigger protecting published result/frame JSON. The startup initializer never resets existing budget counts. Do not reset the database to bypass caps.

## Render Free — Django

- Select a **Free Python web service** linked to the selected repository. Root: `backend`. Build: `bash scripts/render-build.sh`. Start: `bash scripts/render-start.sh`. Health: `/api/v1/health/`. Prepared blueprint: root `render.yaml`; applying it requires authorization.
- Set the private variables from `backend/.env.deployment.example`. Generate a stable random `DJANGO_SECRET_KEY` with at least 50 characters. Set exact hostname(s), the exact HTTPS Pages origin, the Neon URL and only the **SHA-256 hash** of a private random reviewer code. The plaintext reviewer code is delivered separately to authorized reviewers.
- Generate a random code locally with `secrets.token_urlsafe(32)` and hash its exact UTF-8 bytes with SHA-256. Keep it out of URLs, frontend build variables, logs and Git. The UI retains it only in tab memory; a page reload requires re-entry. Rotate by changing the server hash.
- Start with `ATLAS_LIVE_ENABLED=0`, `ATLAS_PUBLIC_WEATHER_CONFIRMED=0`, `ATLAS_PUBLIC_TOMTOM_CONFIRMED=0`. Sample mode needs no provider key. Add `TOMTOM_API_KEY` only in Render's private environment when local credentials are separately authorized for hosted use.
- After the public-use checks and explicit live-release authorization, set all required live switches to 1. Keep the noncommercial scope and snowfall approximation disclosed. This release supports no paid fallback or automatic retry.
- [Render Free](https://render.com/docs/free) has idle spin-down, ephemeral disk, finite hours/traffic allowances and possible outbound-traffic suspension. [Free compute](https://render.com/docs/compute-plans) is 0.1 CPU/512 MB. Neon holds persistence; the health endpoint deliberately performs no DB/provider call. Hosted cold starts and resource behavior must still be measured after deployment.

The backend serves JSON only, so there is no Django admin/static dashboard, WhiteNoise or Node build on Render. Gunicorn uses one worker and two threads, bounded socket timeouts and periodic worker recycling. Startup runs migrations because Free services lack a pre-deploy/shell workflow. Do not start a second overlapping migration service.

Expired-row cleanup runs on startup/new analyses; `python manage.py purge_expired_analyses` removes only expired snapshots and preserves budgets. API expiry is not an exact physical deletion deadline during idle periods, and Neon restore history is separate. Confirm provider retention before public live activation. `check --deploy` leaves W005/W021 visible because the managed hostname is not opted into HSTS subdomain/preload coverage; CSRF and HTTPS protection remain configured.

## Cloudflare Pages Free — frontend

- Choose the selected repository, project root `frontend`, build command `npm run build`, output `dist`, and Node `24.19.0` using `NODE_VERSION`. Use the pinned lockfile. Set only `VITE_API_BASE=https://YOUR-RENDER-SERVICE.onrender.com/api/v1` as public API configuration.
- Do not add reviewer codes, API keys or DB connection strings as `VITE_*` values. The URL must use HTTPS and have no credentials, query or fragment. Pages serves the compiled frontend; there are no paid Functions or proxies.
- Vite copies `public/_headers`, including framing, referrer and CSP headers. Browser workers require `worker-src 'self' blob:`; inline map styles remain allowed. Confirm headers and MapLibre rendering on the actual Pages origin.
- [Cloudflare's React guide](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/) describes the Vite `dist` output. Project and preview origins require explicit backend CORS entries; do not use wildcard preview origins. Do not enable live access for unreviewed preview deployments.

## Hosted acceptance after authorization

1. Verify HTTPS, exact host/CORS rejection, anonymous health, reviewer access and sample mode without keys. Health is liveness, not a DB readiness certification.
2. Verify PostgreSQL snapshots and attempt counts survive a backend restart. Verify Neon pooled TLS, current storage/compute usage and request caps. Do not run pytest against Neon; use the isolated local test database.
3. Only after public permission switches are authorized, run one bounded live three-route analysis. Record ETA weather coverage, provider attempts, timing, ranking and all 49 slider positions. Fewer candidates or Unknown coverage must be disclosed, never disguised as successful assessment completion.
4. Measure actual Render startup/RSS/timeouts and browser/GPU behavior. Do not claim the local Linux measurements represent Render's 0.1 CPU. Check the real Pages CSP and cross-origin requests.
5. Record the 5–10-minute walkthrough after the hosted flow passes. Use the existing walkthrough outline and omit credentials/private account screens. No keep-alive pinger, automatic provider retry or paid upgrade is part of this release.

Repository URL: https://github.com/ShyanCS/Atlas

Pages URL:

Render URL:

Loom URL:
