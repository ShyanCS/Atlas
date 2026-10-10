# Security and assessment scope

Do not post credentials, private account data or provider route geometry in issues or pull requests. Use GitHub's private vulnerability reporting when available; otherwise contact the repository owner privately.

Provider credentials and database access belong only in the backend hosting environment. Reviewer codes never belong in frontend build variables. CI uses authored fixtures, a disposable database and no live-provider credentials.

Hosted live weather/routing are disabled by default. Provider display/retention permissions and public live activation remain separate release checks. Forecast recommendations do not certify road safety, truck-road legality or dock access.

The prepared public-access update permits only three curated example scenarios and their marked immutable snapshots/frames. Existing/private records stay protected even when a UUID is known. Custom POSTs and live geocoding are not anonymous operations. Public reads/builds have fixed durable global caps, no per-attacker cache keys, and no provider I/O. The hosted example switch defaults off until release approval. Shared limits can produce temporary 429 responses under concurrent visitors; this limited free release does not claim full denial-of-service protection.

Dependencies retain their own licenses. No new redistribution license for the assessment source is granted by publication; do not infer commercial Open-Meteo permission from this repository's public visibility.
