"""Localhost-only API smoke evidence; no provider endpoints or credentials."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000/api/v1/"


def request(path, body=None):
    url = BASE + path
    if not url.startswith(BASE):
        raise ValueError("Only the fixed localhost API is allowed")
    data = json.dumps(body).encode() if body is not None else None
    started = time.perf_counter()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read())
            code, request_id = response.status, response.headers.get("X-Request-ID")
            security_headers = {
                key: response.headers.get(key)
                for key in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy")
            }
    except urllib.error.HTTPError as response:
        payload = json.loads(response.read())
        code, request_id = response.code, response.headers.get("X-Request-ID")
        security_headers = {
            key: response.headers.get(key)
            for key in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy")
        }
    return {
        "http_status": code,
        "request_id": request_id,
        "seconds": round(time.perf_counter() - started, 6),
        "security_headers": security_headers,
    }, payload


def main():
    health_event, health = request("health/")
    assert health_event["security_headers"]["X-Frame-Options"] == "DENY"
    assert health_event["security_headers"]["X-Content-Type-Options"] == "nosniff"
    scenario_event, scenarios = request("scenarios/")
    records = []
    for scenario in ("complete", "partial", "no-travel"):
        inputs = {
            "mode": "sample",
            "scenario": scenario,
            **scenarios["locations"],
            "departure_local": scenarios["defaults"]["departure_local"],
            "origin_timezone": scenarios["defaults"]["origin_timezone"],
            "load_weight_lb": scenarios["defaults"]["load_weight_lb"],
            "checkpoint_interval_miles": scenarios["defaults"]["checkpoint_interval_miles"],
        }
        created_event, created = request("analyses/", inputs)
        assert created_event["http_status"] == 201 and created["sample_data"]
        read_event, fetched = request(f"analyses/{created['id']}/")
        assert fetched == created
        frames = []
        for hour, variable in ((0, "wind"), (48, "snow")):
            event, frame = request(
                f"analyses/{created['id']}/frames/?hour={hour}&variable={variable}"
            )
            assert event["http_status"] == 200 and frame["analysis_id"] == created["id"]
            frames.append(
                {
                    **event,
                    "hour": hour,
                    "variable": variable,
                    "coverage": frame["coverage"],
                    "cell_count": len(frame["cells"]),
                    "sample_data": frame["sample_data"],
                }
            )
        _, after = request(f"analyses/{created['id']}/")
        assert after == created
        records.append(
            {
                "scenario": scenario,
                "analysis_id": created["id"],
                "create": created_event,
                "read": read_event,
                "mode": created["mode"],
                "sample_data": created["sample_data"],
                "fixture_version": created["fixture_version"],
                "recommendation": created["recommendation"],
                "checkpoint_counts": {r["id"]: len(r["checkpoints"]) for r in created["routes"]},
                "route_labels": {r["id"]: r["label"] for r in created["routes"]},
                "normalized_local_departure": created["inputs"]["departure_local"],
                "frames": frames,
                "snapshot_unchanged_after_scrub": True,
                "body_sha256": hashlib.sha256(
                    json.dumps(created, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    blocked_event, blocked = request("analyses/", {"mode": "live"})
    assert (
        blocked_event["http_status"] == 503 and blocked["error"]["code"] == "LIVE_MODE_UNAVAILABLE"
    )
    evidence = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Phase 3A local authored samples only",
        "status": "PASS_LOCAL_SAMPLE_API_SMOKE",
        "health": {**health_event, **health},
        "scenarios": scenario_event,
        "analyses": records,
        "live_mode": {**blocked_event, "code": blocked["error"]["code"]},
        "provider_requests": 0,
        "external_hosts_used": [],
        "background_workers": False,
        "schema_sha256": hashlib.sha256((ROOT / "backend/openapi.yaml").read_bytes()).hexdigest(),
        "limitations": [
            "Synthetic data only; live assessment compliance not established",
            "Local development server only",
            "No production authentication or tenancy",
            "Provider/data/license/native snow/free host/browser gates remain open",
        ],
    }
    out = ROOT / "docs/implementation/evidence/backend-foundation-api-smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "scenarios": len(records),
                "live_mode_http": blocked_event["http_status"],
                "provider_requests": 0,
                "evidence_path": str(out.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    )


if __name__ == "__main__":
    main()
