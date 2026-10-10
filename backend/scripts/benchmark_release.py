"""Isolated Linux Gunicorn/PostgreSQL release smoke. Authored samples only.

Run with the disposable test DATABASE_URL, never a Neon or operational database.
No upstream credentials, provider HTTP, raw geometry exports or billing.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8002/api/v1"
CODE = "authored-linux-release-reviewer-code"
env = os.environ.copy()
if "127.0.0.1:55432/atlas_release" not in env.get("DATABASE_URL", ""):
    raise SystemExit("Only the disposable loopback PostgreSQL database is permitted.")
env.update(
    ATLAS_DEPLOYMENT="hosted",
    DJANGO_DEBUG="0",
    DJANGO_SECRET_KEY="authored-isolated-test-secret-" * 3,
    DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost",
    ATLAS_CORS_ORIGINS="https://atlas-assessment.pages.dev",
    ATLAS_ASSESSMENT_ACCESS_HASH=hashlib.sha256(CODE.encode()).hexdigest(),
    ATLAS_LIVE_ENABLED="0",
    ATLAS_PUBLIC_WEATHER_CONFIRMED="0",
    ATLAS_PUBLIC_TOMTOM_CONFIRMED="0",
    TOMTOM_API_KEY="",
)
os.environ.update(env)
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django  # noqa: E402

django.setup()
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

from atlas.models import ProviderRequestBudget  # noqa: E402
from atlas.providers.database_budget import DatabaseAssessmentBudget  # noqa: E402

call_command("check", deploy=True, fail_level="ERROR")
call_command("initialize_assessment_budget")
report = {
    "status": "RUNNING",
    "provider_http_requests": 0,
    "scope": "local Linux; real TLS PostgreSQL; authored sample results only",
    "checks": [],
}
server = None
log = (ROOT / "backend/.local/gunicorn-release.log").open("w")


def request(path, body=None, authorized=True):
    headers = {"X-Forwarded-Proto": "https", "Origin": "https://atlas-assessment.pages.dev"}
    if authorized:
        headers["Authorization"] = "Bearer " + CODE
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            return (
                response.status,
                json.loads(data),
                len(data),
                {k.lower(): v for k, v in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), 0, dict(error.headers)


def start():
    global server
    started = time.perf_counter()
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "config.wsgi:application",
            "--config",
            "gunicorn.conf.py",
            "--bind",
            "127.0.0.1:8002",
        ],
        cwd=ROOT / "backend",
        env=env,
        stdout=log,
        stderr=log,
    )
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError("Gunicorn failed to start; inspect private local log.")
        try:
            status, health, _, _ = request("/health/", authorized=False)
            if status == 200:
                assert health["assessment_access_required"] and not health["live_available"]
                return time.perf_counter() - started
        except urllib.error.URLError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Gunicorn did not become ready")


def rss_kib():
    children_path = Path(f"/proc/{server.pid}/task/{server.pid}/children")
    pids = [server.pid] + [int(p) for p in children_path.read_text().split()]
    return sum(
        int(
            next(
                line.split()[1]
                for line in Path(f"/proc/{pid}/status").read_text().splitlines()
                if line.startswith("VmRSS:")
            )
        )
        for pid in pids
    )


try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone()[0]
        cursor.execute("SHOW server_version")
        report["postgres_version"] = cursor.fetchone()[0]
    report["startup_seconds"] = start()
    assert request("/scenarios/", authorized=False)[0] == 401
    status, scenarios, _, headers = request("/scenarios/")
    assert status == 200 and scenarios["sample_data"]
    assert headers["access-control-allow-origin"] == "https://atlas-assessment.pages.dev"
    data = dict(scenarios["defaults"])
    data.update(
        origin=scenarios["locations"]["origin"],
        destination=scenarios["locations"]["destination"],
        mode="sample",
        scenario="complete",
    )
    started = time.perf_counter()
    status, analysis, _, _ = request("/analyses/", data)
    assert status == 201 and analysis["sample_data"] and len(analysis["routes"]) == 3
    report["sample_analysis_seconds"] = time.perf_counter() - started
    report["gunicorn_master_worker_rss_kib"] = rss_kib()
    identity = analysis["id"]
    report["frame_response_bytes"] = 0
    before = request(f"/analyses/{identity}/")[1]
    started = time.perf_counter()
    for hour in range(49):
        for variable in ("wind", "rain", "snow"):
            status, frame, size, _ = request(
                f"/analyses/{identity}/frames/?hour={hour}&variable={variable}"
            )
            assert status == 200 and frame["analysis_id"] == identity and frame["hour"] == hour
            report["frame_response_bytes"] += size
    report["frame_reads"] = 147
    report["frame_reads_seconds"] = time.perf_counter() - started
    assert request(f"/analyses/{identity}/")[1] == before
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT octet_length(frame_data::text), octet_length((frame_data->'values'->'0')::text) + octet_length((frame_data->'cells')::text) FROM atlas_analysissnapshot WHERE id=%s",
            [identity],
        )
        report["full_frame_series_logical_bytes"], report["selected_hour_cells_logical_bytes"] = (
            cursor.fetchone()
        )
    # Fake budget admission, no upstream request. Demonstrate process-restart durability.
    with DatabaseAssessmentBudget().claim("routing"):
        pass
    counters = ProviderRequestBudget.objects.get(pk="assessment-v1").counts
    server.terminate()
    server.wait(10)
    report["restart_seconds"] = start()
    assert request(f"/analyses/{identity}/")[1] == before
    call_command("initialize_assessment_budget")
    assert ProviderRequestBudget.objects.get(pk="assessment-v1").counts == counters
    assert request("/analyses/", {"mode": "live"})[0] == 503
    report["checks"] = [
        "verified PostgreSQL TLS",
        "Gunicorn hosted startup/check --deploy",
        "reviewer access/CORS/sample without provider credentials",
        "all 147 frame reads preserve ranking",
        "snapshot and finite budget survive process restart",
        "hosted live remains disabled",
    ]
    report["status"] = "PASS"
except Exception as error:
    report["status"] = "FAIL"
    report["failure_class"] = type(error).__name__
    raise
finally:
    if server and server.poll() is None:
        server.terminate()
        server.wait(10)
    log.close()
    (ROOT / "docs/implementation/evidence/deployment-preparation/linux-runtime.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
print(json.dumps(report, indent=2))
