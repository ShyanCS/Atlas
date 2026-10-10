import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from atlas.models import AnalysisSnapshot

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def payload():
    return {
        "mode": "sample",
        "scenario": "complete",
        "origin": {"name": "Chicago, IL", "latitude": "41.8781", "longitude": "-87.6298"},
        "destination": {"name": "Atlanta, GA", "latitude": "33.7490", "longitude": "-84.3880"},
        "departure_local": "2026-10-10T06:00:00",
        "origin_timezone": "America/Chicago",
        "load_weight_lb": "24000",
        "checkpoint_interval_miles": 25,
    }


def create(client, payload):
    response = client.post("/api/v1/analyses/", payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def test_health_and_named_scenarios(client):
    health = client.get("/api/v1/health/")
    assert health.status_code == 200 and health.data["live_available"] is False
    response = client.get("/api/v1/scenarios/")
    assert response.status_code == 200 and response.data["sample_data"] is True
    assert [s["id"] for s in response.data["scenarios"]] == ["complete", "partial", "no-travel"]
    assert response.data["locations"]["origin"]["latitude"] == "41.878100"


@pytest.mark.parametrize(
    "scenario,state",
    [("complete", "recommended"), ("partial", "unverified"), ("no-travel", "blocked")],
)
def test_scenario_analysis_traceability(client, payload, scenario, state):
    payload["scenario"] = scenario
    result = create(client, payload)
    assert result["recommendation"]["state"] == state
    assert result["sample_data"] and result["mode"] == "sample"
    assert result["inputs"]["departure_at"] == "2026-10-10T11:00:00Z"
    assert (
        result["lifecycle"][0]["status"] == "queued"
        and result["lifecycle"][-1]["status"] == "complete"
    )
    assert len(result["routes"]) == 3
    assert result["recommendation"]["route_id"] == ("route-b" if scenario == "complete" else None)
    for route in result["routes"]:
        assert isinstance(route["distance_mi"], str)
        assert abs(
            sum(Decimal(v) for v in route["exposure"].values()) - Decimal(route["distance_mi"])
        ) <= Decimal("0.000003")
        assert (
            route["checkpoints"][0]["label"] == "Start"
            and route["checkpoints"][-1]["label"] == "Finish"
        )
        assert len({cp["id"] for cp in route["checkpoints"]}) == len(route["checkpoints"])
        assert all(cp["route_id"] == route["id"] for cp in route["checkpoints"])
        assert all(
            m["provenance"]["kind"] == "synthetic"
            for cp in route["checkpoints"]
            for m in cp["measurements"].values()
        )
        assert all(cp["rule_explanations"] for cp in route["checkpoints"])
        assert route["routing_eligibility_basis"] == "authored_sample_assumption"
        assert all(len(span["geometry"]["coordinates"]) >= 2 for span in route["risk_spans"])
        assert route["checkpoints"][-1]["eta_utc"] == route["arrival_at"]


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_intervals_are_sampled_with_endpoint_tail(client, payload, interval):
    payload["checkpoint_interval_miles"] = interval
    result = create(client, payload)
    route = result["routes"][0]
    distances = [Decimal(cp["distance_mi"]) for cp in route["checkpoints"]]
    assert distances[0] == 0 and distances[-1] == Decimal(route["distance_mi"])
    assert all(distance == interval * index for index, distance in enumerate(distances[:-1]))


def test_frames_do_not_change_immutable_recommendation(client, payload):
    result = create(client, payload)
    before = client.get(f"/api/v1/analyses/{result['id']}/").data
    for hour in (0, 24, 48):
        for variable in ("wind", "rain", "snow"):
            response = client.get(
                f"/api/v1/analyses/{result['id']}/frames/", {"hour": hour, "variable": variable}
            )
            assert response.status_code == 200
            frame = response.data
            assert (
                frame["analysis_id"] == result["id"]
                and frame["hour"] == hour
                and frame["variable"] == variable
            )
            assert len(frame["cells"]) == frame["coverage"]["total_cells"] == 32
            assert all(
                cell["measurement"]["provenance"]["kind"] == "synthetic" for cell in frame["cells"]
            )
            if variable == "snow" and hour == 48:
                assert (
                    frame["coverage"]["status"] == "missing"
                    and frame["coverage"]["known_cells"] == 0
                )
                assert all(
                    cell["measurement"]["value"] is None and cell["measurement"]["missing_reason"]
                    for cell in frame["cells"]
                )
    assert client.get(f"/api/v1/analyses/{result['id']}/").data == before
    assert (
        client.get(f"/api/v1/analyses/{result['id']}/frames/", {"hour": 0, "variable": "wind"}).data
        == client.get(
            f"/api/v1/analyses/{result['id']}/frames/", {"hour": 0, "variable": "wind"}
        ).data
    )


def test_checkpoint_and_frame_share_the_same_synthetic_source_slots(client, payload):
    result = create(client, payload)
    checkpoint = result["routes"][0]["checkpoints"][0]
    for variable in ("wind", "rain", "snow"):
        frame = client.get(
            f"/api/v1/analyses/{result['id']}/frames/", {"hour": 0, "variable": variable}
        ).data
        assert frame["cells"][0]["measurement"] == checkpoint["measurements"][variable]


def test_native_slot_gap_prevents_false_partial_coverage():
    from datetime import datetime
    from datetime import timezone as utc_zone

    from atlas.services.analysis import source_measurements

    departure = datetime(2026, 10, 10, 11, tzinfo=utc_zone.utc)
    values, measurements = source_measurements(
        route_index=0,
        fraction=Decimal(".4"),
        requested_at=departure + timedelta(hours=5, minutes=45),
        departure_at=departure,
        scenario="partial",
        model_run_at=departure - timedelta(hours=6),
        retrieved_at=departure,
    )
    assert values["snow"] is None
    assert measurements["snow"]["provenance"]["interval_end"] == "2026-10-10T17:00:00Z"
    assert measurements["snow"]["missing_reason"]
    # Canonical measurement strings retain the exact Decimal; UI rounding is separate.
    assert measurements["wind"]["value"] == str(values["wind"])


@pytest.mark.parametrize("mode", ["actual", "live"])
def test_live_mode_returns_typed_unavailable_without_network(client, mode, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Sample API must not create provider connections")

    monkeypatch.setattr("socket.create_connection", forbidden)
    response = client.post("/api/v1/analyses/", {"mode": mode}, format="json")
    assert response.status_code == 503 and response.data["error"]["code"] == "LIVE_MODE_UNAVAILABLE"
    assert AnalysisSnapshot.objects.count() == 0


@pytest.mark.parametrize(
    "change",
    [
        {"checkpoint_interval_miles": 15},
        {"load_weight_lb": "-1"},
        {"load_weight_lb": "NaN"},
        {"unexpected": "discard me"},
        {"mode": []},
    ],
)
def test_invalid_input_is_rejected_before_snapshot(client, payload, change):
    payload.update(change)
    response = client.post("/api/v1/analyses/", payload, format="json")
    assert response.status_code == 400 and response.data["error"]["code"] == "VALIDATION_ERROR"
    assert AnalysisSnapshot.objects.count() == 0


def test_arbitrary_location_is_not_fake_geocoded(client, payload):
    payload["origin"]["name"] = "New York, NY"
    response = client.post("/api/v1/analyses/", payload, format="json")
    assert (
        response.status_code == 400
        and response.data["error"]["code"] == "SAMPLE_LOCATION_UNAVAILABLE"
    )


def test_dst_fold_and_nonexistent_local_time(client, payload):
    payload["departure_local"] = "2026-11-01T01:30:00"
    ambiguous = client.post("/api/v1/analyses/", payload, format="json")
    assert (
        ambiguous.status_code == 400
        and ambiguous.data["error"]["code"] == "DEPARTURE_TIME_AMBIGUOUS"
    )
    payload["departure_fold"] = 0
    first = create(client, payload)
    payload["departure_fold"] = 1
    second = create(client, payload)
    assert (
        first["inputs"]["departure_at"] == "2026-11-01T06:30:00Z"
        and second["inputs"]["departure_at"] == "2026-11-01T07:30:00Z"
    )
    payload.pop("departure_fold")
    payload["departure_local"] = "2026-03-08T02:30:00"
    nonexistent = client.post("/api/v1/analyses/", payload, format="json")
    assert (
        nonexistent.status_code == 400
        and nonexistent.data["error"]["code"] == "DEPARTURE_TIME_NONEXISTENT"
    )


def test_absolute_and_local_departure_must_agree(client, payload):
    payload["departure_at"] = "2026-10-10T12:00:00Z"
    response = client.post("/api/v1/analyses/", payload, format="json")
    assert (
        response.status_code == 400
        and response.data["error"]["code"] == "DEPARTURE_TIME_INCONSISTENT"
    )


def test_utc_only_input_normalizes_local_display_and_occurrence(client, payload):
    payload.pop("departure_local")
    payload["departure_at"] = "2026-10-10T11:00:00Z"
    result = create(client, payload)
    assert (
        result["inputs"]["departure_local"] == "2026-10-10T06:00:00"
        and result["inputs"]["departure_fold"] is None
    )
    payload["departure_at"] = "2026-11-01T07:30:00Z"
    folded = create(client, payload)
    assert (
        folded["inputs"]["departure_local"] == "2026-11-01T01:30:00"
        and folded["inputs"]["departure_fold"] == 1
    )


@pytest.mark.parametrize(
    "departure_field,value,zone",
    [
        ("departure_at", "0001-01-01T00:00:00Z", "UTC"),
        ("departure_at", "9999-12-31T20:00:00Z", "UTC"),
        ("departure_at", "0001-01-01T00:00:00+14:00", "UTC"),
        ("departure_at", "9999-12-31T23:00:00-12:00", "UTC"),
        ("departure_local", "0001-01-01T00:00:00", "Asia/Kolkata"),
        ("departure_local", "9999-12-31T23:00:00", "America/Chicago"),
        ("departure_at", "0001-01-01T06:00:00Z", "Etc/GMT+12"),
        ("departure_at", "0001-01-01T05:59:59.999999Z", "UTC"),
        ("departure_at", "9999-12-29T22:00:00Z", "UTC"),
    ],
)
def test_unrepresentable_departure_returns_typed_error_before_snapshot(
    client, payload, departure_field, value, zone
):
    payload.pop("departure_local")
    payload[departure_field] = value
    payload["origin_timezone"] = zone
    response = client.post("/api/v1/analyses/", payload, format="json")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "DEPARTURE_TIME_UNSUPPORTED"
    assert response.data["request_id"]
    assert AnalysisSnapshot.objects.count() == 0


@pytest.mark.parametrize(
    "departure",
    ["0001-01-01T06:00:00Z", "9999-12-29T21:59:59.999999Z"],
)
def test_representable_sample_calendar_boundaries_still_complete(client, payload, departure):
    payload.pop("departure_local")
    payload["departure_at"] = departure
    payload["origin_timezone"] = "UTC"
    result = create(client, payload)
    assert result["inputs"]["departure_at"] == departure
    frame = client.get(f"/api/v1/analyses/{result['id']}/frames/?hour=48&variable=wind")
    assert frame.status_code == 200 and frame.data["hour"] == 48


def test_unknown_id_expiry_and_local_admission(client, payload):
    assert client.get(f"/api/v1/analyses/{uuid.uuid4()}/").status_code == 404
    with override_settings(ATLAS_MAX_LOCAL_SNAPSHOTS=1):
        result = create(client, payload)
        limited = client.post("/api/v1/analyses/", payload, format="json")
        assert (
            limited.status_code == 429 and limited.data["error"]["code"] == "SAMPLE_ADMISSION_LIMIT"
        )
        AnalysisSnapshot.objects.filter(id=result["id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert client.get(f"/api/v1/analyses/{result['id']}/").status_code == 410
        assert create(client, payload)["id"] != result["id"]


def test_frame_bounds_and_request_ids(client, payload):
    request_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/analyses/", payload, format="json", HTTP_X_REQUEST_ID=request_id
    )
    assert response["X-Request-ID"] == request_id
    for query in (
        {"hour": -1, "variable": "wind"},
        {"hour": 49, "variable": "wind"},
        {"hour": "1.5", "variable": "wind"},
        {"hour": 1, "variable": "risk"},
        {"hour": 1, "variable": "wind", "extent": "world"},
    ):
        frame = client.get(f"/api/v1/analyses/{response.data['id']}/frames/", query)
        assert frame.status_code == 400 and frame.data["request_id"]
    assert (
        client.get(
            f"/api/v1/analyses/{response.data['id']}/frames/?hour=0&hour=1&variable=wind"
        ).status_code
        == 400
    )
    assert (
        client.get("/api/v1/health/", HTTP_X_REQUEST_ID="not a uuid")["X-Request-ID"]
        != "not a uuid"
    )


def test_body_limit_and_cors(client):
    large = client.post(
        "/api/v1/analyses/",
        data='{"padding":"' + "x" * 17000 + '"}',
        content_type="application/json",
    )
    assert large.status_code == 413
    assert large["X-Frame-Options"] == "DENY" and large["X-Content-Type-Options"] == "nosniff"
    allowed = client.get("/api/v1/health/", HTTP_ORIGIN="http://127.0.0.1:5173")
    assert allowed["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert allowed["X-Frame-Options"] == "DENY" and allowed["X-Content-Type-Options"] == "nosniff"
    assert allowed["Referrer-Policy"] == "same-origin"
    forbidden = client.get("/api/v1/health/", HTTP_ORIGIN="https://unrelated.example")
    assert "Access-Control-Allow-Origin" not in forbidden


def test_unknown_route_and_django_log_formatter_do_not_echo_inputs(client):
    import logging

    from atlas.middleware import SafeJsonFormatter

    response = client.get("/api/v1/does-not-exist/?token=synthetic-private-text")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    assert "synthetic-private-text" not in response.content.decode()
    record = logging.LogRecord(
        "django.server", logging.WARNING, "", 0, "GET /?token=synthetic-private-text", (), None
    )
    assert "synthetic-private-text" not in SafeJsonFormatter().format(record)


def test_openapi_has_typed_contract_and_no_auth_requirement(client):
    response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    schema = response.data
    names = schema["components"]["schemas"]
    assert {
        "Analysis",
        "AnalysisInputRequest",
        "Route",
        "Checkpoint",
        "Measurement",
        "Frame",
        "LineGeometry",
        "PolygonGeometry",
    } <= set(names)
    assert names["LineGeometry"]["properties"]["coordinates"]["items"]["items"]["type"] == "number"
    assert schema["paths"]["/api/v1/analyses/"]["post"].get("security", []) in ([], [{}])
