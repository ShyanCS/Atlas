"""Explicit local launcher/probe. Loads only TomTom key, never prints secret values.

Usage: python scripts/local_assessment.py serve | probe
Local env loading does not integrate WeatherAPI's Business trial or native codecs.
"""

import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
for line in (
    (ROOT / ".env.feasibility").read_text().splitlines()
    if (ROOT / ".env.feasibility").exists()
    else ()
):
    if line.startswith("TOMTOM_API_KEY=") and not os.environ.get("TOMTOM_API_KEY"):
        os.environ["TOMTOM_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# This launcher's purpose is the explicitly authorized personal assessment.
for name in (
    "ATLAS_LIVE_ENABLED",
    "ATLAS_NONCOMMERCIAL_ASSESSMENT",
    "ATLAS_ACCEPT_PROVIDER_SNOWFALL",
):
    os.environ.setdefault(name, "1")

import django  # noqa: E402 -- environment set before Django initialization

django.setup()
from django.core.management import execute_from_command_line  # noqa: E402

if len(sys.argv) != 2 or sys.argv[1] not in {"serve", "probe", "probe-existing"}:
    raise SystemExit("Usage: local_assessment.py serve | probe | probe-existing")
if sys.argv[1] == "serve":
    port = int(os.environ.get("ATLAS_LOCAL_PORT", "8000"))
    if not 1024 <= port <= 65535:
        raise SystemExit("Invalid local port")
    execute_from_command_line(["manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"])
else:
    evidence_subdir = os.environ.get("ATLAS_PROBE_EVIDENCE_SUBDIR", "assessment-json")
    if evidence_subdir not in {"assessment-json", "deployment-preparation"}:
        raise SystemExit("Invalid local evidence directory")
    from django.utils import timezone
    from rest_framework.test import APIClient

    client = APIClient()
    start = time.perf_counter()
    from django.conf import settings

    budget_path = Path(settings.ATLAS_PROVIDER_BUDGET_PATH)
    before = (
        json.loads(budget_path.read_text())["counts"]
        if budget_path.exists()
        else dict.fromkeys(("routing", "geocoding", "weather"), 0)
    )
    locations = []
    private = ROOT / "backend/.local"
    private.mkdir(exist_ok=True)
    for text in ("Dallas Texas", "Houston Texas") if sys.argv[1] == "probe" else ():
        response = client.post("/api/v1/locations/geocode/", {"text": text}, format="json")
        if response.status_code != 200 or not response.data:
            raise SystemExit("Geocoding failed: " + str(response.status_code))
        place = response.data[0]
        locations.append({k: place[k] for k in ("name", "latitude", "longitude")})
    if sys.argv[1] == "probe-existing":
        locations = json.loads((private / "probe-locations.json").read_text())
    else:
        (private / "probe-locations.json").write_text(json.dumps(locations))
    response = client.post(
        "/api/v1/analyses/",
        {
            "mode": "live",
            "origin": locations[0],
            "destination": locations[1],
            "departure_at": (
                timezone.now().replace(microsecond=0) + timedelta(hours=1)
            ).isoformat(),
            "origin_timezone": "America/Chicago",
            "load_weight_lb": "24000",
            "checkpoint_interval_miles": 25,
            "truck_profile": {
                "current_weight_kg": 36000,
                "height_m": "4.1",
                "width_m": "2.6",
                "length_m": "21",
                "axle_weight_kg": 9000,
                "axle_count": 4,
            },
        },
        format="json",
    )
    after = json.loads(budget_path.read_text())["counts"]
    summary = {
        "observed_at": timezone.now().isoformat(),
        "seconds": time.perf_counter() - start,
        "http_status": response.status_code,
        "request_counts": {key: after[key] - before[key] for key in before},
        "scope": "local noncommercial assessment; no provider geometry in evidence",
    }
    if response.status_code == 201:
        analysis = response.data
        summary.update(
            {
                "analysis_id": analysis["id"],
                "mode": analysis["mode"],
                "sample_data": analysis["sample_data"],
                "policy_version": analysis["policy_version"],
                "route_count": len(analysis["routes"]),
                "recommendation_state": analysis["recommendation"]["state"],
                "recommended_route_id": analysis["recommendation"]["route_id"],
                "routes": [
                    {
                        k: r[k]
                        for k in (
                            "id",
                            "distance_mi",
                            "duration_seconds",
                            "eligible",
                            "eligibility_reasons",
                            "verified_fraction",
                            "route_notices",
                        )
                    }
                    | {"checkpoint_count": len(r["checkpoints"])}
                    for r in analysis["routes"]
                ],
            }
        )
        checked = []
        for hour in range(49):
            for variable in ("wind", "rain", "snow"):
                frame = client.get(
                    f"/api/v1/analyses/{analysis['id']}/frames/?hour={hour}&variable={variable}"
                )
                if frame.status_code != 200:
                    raise SystemExit("Stored frame read failed")
                checked.append(frame.data["coverage"]["status"])
        summary["stored_frame_reads"] = len(checked)
        summary["complete_frames"] = checked.count("complete")
        private = ROOT / "backend/.local"
        private.mkdir(exist_ok=True)
        (private / "last-live-id.txt").write_text(analysis["id"])
        summary["status"] = (
            "PASS"
            if len(analysis["routes"]) == 3 and all(r["eligible"] for r in analysis["routes"])
            else "INCOMPLETE"
        )
    else:
        summary["status"] = "FAIL"
        summary["error_code"] = response.data.get("error", {}).get("code")
        summary["error_details"] = response.data.get("error", {}).get("details")
    out = ROOT / "docs/implementation/evidence" / evidence_subdir
    out.mkdir(parents=True, exist_ok=True)
    filename = (
        "first-live-analysis.json"
        if evidence_subdir == "assessment-json"
        else "live-regression.json"
    )
    (out / filename).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
