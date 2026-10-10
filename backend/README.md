# Spotter Atlas Django API

Modular monolith with backend-authoritative deterministic risk calculations. Local mode defaults to labeled sample fixtures; explicitly authorized live mode uses the normalized TomTom and Open-Meteo adapters. Hosted live use remains disabled until separate public-source release checks pass.

The public-example service serves three fixed trips through `GET /api/v1/examples/{scenario}/`. Their shared snapshots have a server-assigned immutable public marker; existing and custom records remain private. Public examples default on locally and off in hosted configuration; the published release explicitly enables them. The private access hash is still mandatory on hosted Django for all protected operations. See [the API contract](API_CONTRACT.md) for durable anonymous limits and scope enforcement.

| Module             | Ownership                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| `atlas/domain/`    | Pure thresholds, load overrides, time matching, route geometry/ETA, midpoint exposure and ranking |
| `atlas/providers/` | Sample fixtures, normalized provider adapters, bounded transport and durable request budgets      |
| `atlas/services/`  | Shared analysis orchestration and immutable result/frame reads                                    |
| `atlas/api/`       | Input validation, response contracts, typed errors and conditional access schema                  |
| `atlas/models.py`  | Short-lived snapshots and separate persistent attempt/request-window rows                         |
| `config/`          | Local defaults, PostgreSQL URLs and fail-closed hosted security settings                          |

## Local sample setup

Use Python 3.12. From `backend/`:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```

On Windows, substitute `.venv/Scripts/python.exe`. Sample mode requires no provider credentials. Environment examples contain placeholders only; settings read process variables. Never publish filled environment files or SQLite/PostgreSQL data.

## Verification

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
```

To exercise PostgreSQL-only cases, use a disposable local test database via `DATABASE_URL`; pytest creates its own test database. Never point pytest at a hosted application database.

[API contracts](API_CONTRACT.md) · [Public source readiness](../docs/deployment/READINESS.md) · [Deployment configuration](../docs/deployment/SETUP.md)

The risk policy remains `atlas-assessment-policy-v1.0.0`. No native weather decoder, arbitrary AI scoring, enterprise identity service or deployment automation is incorporated. Published calculations and forecast-clock views share the same analysis identity; route selection cannot change the recommendation.
