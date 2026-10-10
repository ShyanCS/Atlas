# Spotter Atlas product experience and public-access update

11 October 2026. **Prepared and verified locally; not pushed, merged or deployed.** The hosted URL still serves its previously approved private-access revision. No provider permissions, billing settings or hosted environment variables changed.

## Product experience

The application opens into Dispatch Canvas and loads the Chicago–Atlanta example without an access screen or creation POST. One contextual **Example trip** indicator sits beside the trip heading. Source Details explains illustrative geometry/weather; it retains timestamps, provenance, missing values, weather approximation and attribution for actual provider-backed results.

Plan Route opens the existing real-trip workflow with origin/destination, departure, cargo, checkpoint spacing and the separate truck profile. A restricted hosted operation is explained only when attempted, retaining draft inputs and the previous analysis. Curated example parameters are fixed; changing Weather scenario selects the corresponding shared server result. Custom calculations remain protected, including arbitrary sample submissions. No disabled provider operation is disguised as successful planning.

Header, route inspector, wind captions, map popups/accessible labels, forecast status, driver briefing and navigation now use ordinary product language. Repeated Demo Mode and assessment identity text is removed. Inactive premium-feature placeholders are removed from navigation. The browser title/description were already product-focused and remain so. Atlas Noir composition, route identities, risk segments, keyboard interaction, map attribution, responsive scrolling and reduced motion remain intact.

The README and current setup/security/API guides explain the prepared behavior and distinguish it from the older hosted revision. Historical design, feasibility, licensing, deployment reports and experiments are unchanged. Proposed GitHub description after publication approval: **Weather-aware truck routing with checkpoint forecasts, deterministic risk recommendations and an interactive Atlas Noir dispatch map. React + Django.** No GitHub metadata was changed in this task.

## Server boundary

| Function                                                     | Prepared access                                                                                              |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Frontend and health                                          | Public; health is non-sensitive liveness                                                                     |
| Scenario descriptions                                        | Anonymous when public examples are enabled; durable read cap                                                 |
| Three curated example analyses                               | Fixed-input GET; no request body/query customization or provider I/O                                         |
| Marked example snapshots/frames                              | Public only when server marker, sample mode, synthetic-data flag, fixture version and completed status agree |
| Custom analysis POST, geocoding, live acquisition            | Existing bearer authorization and provider caps remain                                                       |
| Existing/private saved analyses, schema and operational docs | Protected even when the UUID is known                                                                        |

Migration `0004_curated_example_access` adds a nullable unique public-example key. Existing rows remain null/private; no user serializer accepts the key. PostgreSQL's published-result guard also prevents changes to that access marker. Three fixed keys bound public storage to three snapshots beyond the existing private admission limit. Shared snapshots refresh only after expiry and are serialized using a fixed database lock row; concurrent visitors produce one result.

Anonymous reads have a durable shared **240/minute** ceiling. Public builds have a shared **3/minute** ceiling. Fixed bucket keys prevent attacker-created quota rows; private UUID checks are charged before lookup. Storage failures fail closed. These global limits may temporarily affect multiple visitors and do not claim complete denial-of-service protection. Provider ledgers and limits are unchanged.

`ATLAS_PUBLIC_EXAMPLES_ENABLED` defaults **1 locally / 0 when hosted**. Hosted startup still requires the protected-access hash, verified PostgreSQL TLS and exact CORS. Locally open provider development remains loopback-only; the release-security tests use an authored private hash. No hosted live switch is enabled.

## Executed verification

- PostgreSQL 16.2, isolated local Linux runtime: **297 backend tests passed**, including immutable access scope, concurrent example cache construction, private records with identical example inputs, source/mode manipulation, schema security, quotas, missing/Unknown weather and existing pure-domain regressions.
- SQLite full regression: **292 passed, four PostgreSQL-only skips** before the added schema assertion; subsequent focused public-access tests passed **22 cases with two PostgreSQL-only skips**. PostgreSQL executed every final backend case with no skips.
- Frontend: **46 tests passed**; ESLint, TypeScript, Prettier, production Vite build and generated API contracts verified. New direct-entry/transport tests replace obsolete access-screen expectations; authorization transport and legacy protected-mode tests remain.
- Browser regression: **13 existing check groups passed** after adapting entry/scenario actions. Coverage retains recommendation immutability, arrival/raw legends, Unknown, No Travel, DST validation, quota/draft recovery, dialogs, mobile navigation, reduced motion and simulated WebGL loss/failure.
- Public-access release browser: **12 passing check groups**, desktop **1440×900** and mobile **390×844**, actual local Django responses, all **147 variable/hour combinations**, no onboarding code, source labeling, restricted real-planning action, CSP and reload without creating per-visitor analyses. The default-view copy check rejects demo/assessment/reviewer branding while allowing the preserved internal policy identifier.
- Cold-start feedback uses a controlled **6.5-second** delay of the actual local scenario response. It is not an actual Render idle cold-start measurement. Chrome uses SwiftShader, not a certified physical GPU/device.
- No domain/risk-policy/provider-adapter files were changed. No real TomTom or weather-provider call was made. Secret scanning and evidence/link validation are recorded beside the screenshots.

The 74 changed/new review files and 14 built assets passed the known-secret/private-path scan with zero matches; all 49 local documentation links resolve, evidence JSON parses and `git diff --check` passes. The existing MapLibre chunk-size warning remains; this cleanup adds no renderer or production dependency. The temporary PostgreSQL server was stopped after verification. The local review UI remains available at <http://127.0.0.1:4177>; its restricted planner cannot access providers without authorization.

[Before/after review gallery](evidence/product-access-cleanup/README.md). Expected quota failures and simulated GPU failures are explicitly labeled in browser evidence; they are not provider performance claims.

## Approval and coordinated release

Approve **source push, PR/description update and coordinated backend/frontend publication with anonymous curated examples**. This approval must not activate hosted live providers or merge main implicitly.

After approval: push the sanitized changes; wait for required CI; deploy Render code/migration with `ATLAS_PUBLIC_EXAMPLES_ENABLED=1` and the existing private hash retained; keep live/public-provider flags at 0 and install no provider key; verify private rejection and shared public cache; publish the matching Pages build using the existing Node 24/API command; verify the actual hosted anonymous desktop/mobile workflow. Update current release documentation to the observed deployed revisions only after those checks pass.

Rollback disables public examples and restores the previous frontend revision; keep the additive schema migration and private hash. No migration of existing records to public is performed. Existing analyses, provider budgets, experiments and historical evidence are preserved.
