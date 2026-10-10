"""Original authored responses only; no retained/redistributed provider geometry."""

import io
import json
import urllib.error
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.domain import GeoPoint, prepare_geometry, sample_chainages
from atlas.providers.interfaces import RoutingQuery
from atlas.providers.tomtom import (
    TomTomAdapter,
    commit_location,
    normalize_geocoding,
    normalize_routing,
)
from atlas.providers.tomtom_http import Gate2TomTomBudget, ProviderError, TomTomHTTP

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def query(**changes):
    original = RoutingQuery(GeoPoint(40, -90), GeoPoint(40, -89.98), NOW)
    return replace(original, **changes)


def route(offset=0, *, duration=1800, distance=4000):
    return {
        "summary": {
            "lengthInMeters": distance,
            "travelTimeInSeconds": duration,
            "departureTime": NOW.isoformat(),
            "arrivalTime": (NOW + timedelta(seconds=duration)).isoformat(),
        },
        "legs": [
            {
                "points": [
                    {"latitude": 40, "longitude": -90},
                    {"latitude": 40 + offset, "longitude": -89.99},
                    {"latitude": 40, "longitude": -89.98},
                ]
            }
        ],
        "progress": [
            {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
            {
                "pointIndex": 1,
                "distanceInMeters": distance / 2,
                "travelTimeInSeconds": duration / 3,
            },
            {"pointIndex": 2, "distanceInMeters": distance, "travelTimeInSeconds": duration},
        ],
        "sections": [
            {
                "startPointIndex": 0,
                "endPointIndex": 2,
                "sectionType": "TRAVEL_MODE",
                "travelMode": "truck",
            }
        ],
    }


def result(*routes, **extra):
    return {"routes": list(routes), **extra}


def test_three_distinct_original_indexes_and_progress():
    batch = normalize_routing(result(route(0), route(0.01), route(-0.01)), query())
    assert batch.three_candidate_requirement_met
    assert [r.candidate_index for r in batch.routes] == [0, 1, 2]
    r = batch.routes[0]
    prepared = prepare_geometry(r.points, r.progress)
    midpoint = prepared.place(Decimal(2000), NOW)
    assert midpoint.eta_utc == NOW + timedelta(seconds=600)
    assert prepared.place(r.distance_m, NOW).eta_utc == r.arrival_at
    assert sample_chainages(r.distance_m, 10) == (Decimal(0), Decimal(4000))
    assert r.requested_origin == r.routing_origin == r.resolved_origin
    assert "latitude" not in repr(r)


@pytest.mark.parametrize("count", [1, 2])
def test_fewer_alternatives_not_fabricated(count):
    batch = normalize_routing(result(*[route(i * 0.01) for i in range(count)]), query())
    assert batch.returned_count == batch.usable_unique_count == count
    assert not batch.three_candidate_requirement_met


def test_duplicates_and_near_jitter_quarantined():
    batch = normalize_routing(result(route(), route(), route(0.00001)), query())
    assert [r.duplicate_of for r in batch.routes] == [None, 0, 0]
    assert batch.usable_unique_count == 1


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"routes": None}, {"routes": []}, {"routes": [route()] * 4}]
)
def test_malformed_top_response(payload):
    with pytest.raises(ProviderError):
        normalize_routing(payload, query())


@pytest.mark.parametrize(
    "point",
    [
        {"latitude": 91, "longitude": 0},
        {"latitude": True, "longitude": 0},
        {"latitude": "NaN", "longitude": 0},
        {},
    ],
)
def test_invalid_geometry_rejected_without_changing_other_index(point):
    bad = route()
    bad["legs"][0]["points"][1] = point
    batch = normalize_routing(result(bad, route(0.01)), query())
    assert batch.rejected[0].candidate_index == 0
    assert batch.routes[0].candidate_index == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("lengthInMeters", 0),
        ("lengthInMeters", -1),
        ("travelTimeInSeconds", True),
        ("travelTimeInSeconds", "Infinity"),
    ],
)
def test_bad_summary_rejected(field, value):
    bad = route()
    bad["summary"][field] = value
    assert normalize_routing(result(bad), query()).rejected


@pytest.mark.parametrize("modify", ["missing", "descending", "summary", "indexes", "time"])
def test_missing_invalid_progress_never_global_speed_fallback(modify):
    bad = route()
    if modify == "missing":
        bad.pop("progress")
    elif modify == "descending":
        bad["progress"][1]["distanceInMeters"] = 5000
    elif modify == "summary":
        bad["progress"][-1]["travelTimeInSeconds"] = 1799
    elif modify == "indexes":
        bad["progress"][1]["pointIndex"] = True
    else:
        bad["summary"]["arrivalTime"] = (NOW + timedelta(hours=10)).isoformat()
    r = normalize_routing(result(bad), query()).routes[0]
    assert r.geometry_valid and not r.timing_valid


@pytest.mark.parametrize("mode", ["other", "car", "pedestrian", None])
def test_non_truck_sections_incompatible(mode):
    bad = route()
    bad["sections"][0]["travelMode"] = mode
    r = normalize_routing(result(bad), query()).routes[0]
    assert not r.routing_valid
    assert json.loads(r.original_sections_json)[0]["travelMode"] == mode


@pytest.mark.parametrize(
    "sections",
    [
        [],
        None,
        [
            {
                "startPointIndex": 0,
                "endPointIndex": 1,
                "sectionType": "TRAVEL_MODE",
                "travelMode": "truck",
            }
        ],
        [
            {
                "startPointIndex": True,
                "endPointIndex": 2,
                "sectionType": "TRAVEL_MODE",
                "travelMode": "truck",
            }
        ],
    ],
)
def test_section_coverage_required(sections):
    bad = route()
    bad["sections"] = sections
    assert not normalize_routing(result(bad), query()).routes[0].routing_valid


@pytest.mark.parametrize(
    "notice",
    [
        {"code": "ROAD_CLOSED", "severity": "info", "message": "Authored road closure"},
        {"code": "NEW_CRITICAL", "severity": "critical"},
        {"code": "UNREVIEWED", "severity": "warning"},
    ],
)
def test_hard_unknown_notices_preserved_and_fail_closed(notice):
    bad = route()
    bad["warnings"] = [notice]
    r = normalize_routing(result(bad), query()).routes[0]
    assert not r.routing_valid and json.loads(r.original_notices_json) == [notice]
    assert r.notices[0].code == notice["code"]
    with pytest.raises(FrozenInstanceError):
        r.notices[0].code = "changed"


def test_information_notice_not_discarded_and_extra_fields_tolerated():
    note = {
        "code": "TEST_INFORMATION",
        "severity": "info",
        "message": "Original owned test notice",
        "additional": 4,
    }
    r = normalize_routing(
        result(
            route(),
            notices=[note],
            report={"effectiveSettings": [{"key": "travelMode", "value": "truck"}]},
        ),
        query(),
    ).routes[0]
    assert r.routing_valid and json.loads(r.original_notices_json)[0]["additional"] == 4


class Spy:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, operation, path, parameters):
        self.calls.append((operation, path, parameters))
        return self.payload


def test_truck_parameters_no_cargo_substitution():
    spy = Spy(result(route()))
    adapter = TomTomAdapter(spy)
    adapter.routes(
        query(truck_restrictions={"current_weight_kg": Decimal(36000), "height_m": Decimal("4.1")})
    )
    params = spy.calls[0][2]
    assert ("vehicleWeight", "36000") in params and ("vehicleCommercial", "true") in params
    assert ("extendedRouteRepresentation", "distance") in params and (
        "extendedRouteRepresentation",
        "travelTime",
    ) in params
    assert not any("cargo" in name.lower() for name, _ in params)


@pytest.mark.parametrize(
    "profile",
    [
        {"cargo_weight_lb": 30000},
        {"height_m": -1},
        {"current_weight_kg": Decimal("36000.1")},
        {"axle_count": True},
    ],
)
def test_profile_rejected_before_request(profile):
    spy = Spy(result(route()))
    with pytest.raises(ProviderError):
        TomTomAdapter(spy).routes(query(truck_restrictions=profile))
    assert not spy.calls


def geocode_payload(**extra):
    return {
        "results": [
            {
                "id": "authored-location",
                "position": {"lat": 40, "lon": -90},
                "address": {"freeformAddress": "Authored test location"},
                "entryPoints": [{"type": "main", "position": {"lat": 40.001, "lon": -90}}],
                **extra,
            }
        ]
    }


def test_geocode_and_explicit_truck_access_commit_preserves_original():
    candidate = normalize_geocoding(geocode_payload())[0]
    original = candidate.position
    with pytest.raises(ProviderError, match="ACCESS_CORRECTION_NOT_CONFIRMED"):
        commit_location(
            candidate,
            requested_coordinate=original,
            timezone_name="America/Chicago",
            access_coordinate=candidate.entry_points[0],
        )
    committed = commit_location(
        candidate,
        requested_coordinate=original,
        timezone_name="America/Chicago",
        access_coordinate=candidate.entry_points[0],
        confirm_correction=True,
        access_basis="explicit_test_selection",
    )
    assert (
        committed.requested_coordinate == original
        and committed.routing_access_coordinate != original
    )
    assert committed.displacement_m > 0 and committed.timezone_basis == "explicit_caller"
    q = query(origin=committed.routing_access_coordinate, requested_origin=original)
    with pytest.raises(ProviderError, match="ACCESS_CORRECTION_NOT_CONFIRMED"):
        TomTomAdapter(Spy(result(route()))).routes(q)
    corrected = normalize_routing(
        result(route()), replace(q, access_corrections_confirmed=True)
    ).routes[0]
    assert (
        corrected.requested_origin == original
        and corrected.routing_origin == committed.routing_access_coordinate
    )


@pytest.mark.parametrize("zone", [None, "not/a/zone"])
def test_timezone_must_be_explicit(zone):
    with pytest.raises(ProviderError, match="EXPLICIT_TIMEZONE_REQUIRED"):
        commit_location(
            normalize_geocoding(geocode_payload())[0],
            requested_coordinate=GeoPoint(40, -90),
            timezone_name=zone,
        )


def test_timezone_mismatch_and_geocode_no_result():
    assert normalize_geocoding({"results": []}) == ()
    candidate = normalize_geocoding(geocode_payload(timeZone={"ianaId": "America/Chicago"}))[0]
    with pytest.raises(ProviderError, match="TIMEZONE_CONFIRMATION_MISMATCH"):
        commit_location(
            candidate, requested_coordinate=candidate.position, timezone_name="America/New_York"
        )


@pytest.mark.parametrize("payload", [None, {}, {"results": [{}]}, geocode_payload(timeZone="bad")])
def test_malformed_geocode(payload):
    with pytest.raises(ProviderError):
        normalize_geocoding(payload)


def test_address_path_escaped_and_control_characters_rejected():
    spy = Spy(geocode_payload())
    TomTomAdapter(spy).geocode("Authored A/B ?address")
    assert "%2F" in spy.calls[0][1] and "%3F" in spy.calls[0][1]
    with pytest.raises(ProviderError):
        TomTomAdapter(spy).geocode("bad\ninput")


def test_budget_durable_caps_and_single_concurrency(tmp_path):
    path = tmp_path / "budget.json"
    budget = Gate2TomTomBudget(path)
    with budget.claim("routing"):
        with pytest.raises(ProviderError, match="PROVIDER_BUSY"):
            with Gate2TomTomBudget(path).claim("geocoding"):
                pass
    for _ in range(5):
        with Gate2TomTomBudget(path).claim("routing"):
            pass
    with pytest.raises(ProviderError, match="MILESTONE_REQUEST_CAP"):
        with budget.claim("routing"):
            pass
    assert budget.read()["routing"] == 6 and budget.read()["geocoding"] == 0


class HttpOpener:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status, self.body, self.headers = status, body, headers or {}
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if self.status != 200:
            raise urllib.error.HTTPError(
                request.full_url,
                self.status,
                "untrusted private detail",
                self.headers,
                io.BytesIO(b"private body"),
            )
        response = io.BytesIO(self.body)
        response.status = 200
        response.headers = self.headers
        return response


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "PROVIDER_UNAUTHORIZED"),
        (403, "PROVIDER_FORBIDDEN"),
        (429, "PROVIDER_QUOTA"),
        (400, "PROVIDER_BAD_INPUT"),
        (500, "PROVIDER_HTTP_ERROR"),
    ],
)
def test_http_failure_no_retry_no_secret(tmp_path, status, code):
    opener = HttpOpener(status, headers={"Retry-After": "20"})
    budget = Gate2TomTomBudget(tmp_path / "budget.json")
    client = TomTomHTTP("owned-fake-test-key", budget, opener=opener)
    with pytest.raises(ProviderError) as caught:
        client.get_json("routing", "/routing/1/calculateRoute/0,0:1,1/json", [])
    assert caught.value.code == code and "key" not in str(caught.value).lower()
    assert caught.value.retry_after == "20" and opener.calls == 1
    if status in (401, 403, 429):
        with pytest.raises(ProviderError):
            client.get_json("geocoding", "/search/2/geocode/test.json", [])
        assert opener.calls == 1


def test_credential_redaction_bad_json_and_path_guard(tmp_path):
    budget = Gate2TomTomBudget(tmp_path / "budget.json")
    opener = HttpOpener(body=b'{"echo":"owned-fake-test-key"}')
    client = TomTomHTTP("owned-fake-test-key", budget, opener=opener)
    assert client.get_json("geocoding", "/search/2/geocode/test.json", []) == {"echo": "[REDACTED]"}
    with pytest.raises(ProviderError, match="UNAPPROVED_PROVIDER_PATH"):
        client.get_json("routing", "/other?key=leak", [])
    opener.body = b'{"bad":NaN}'
    with pytest.raises(ProviderError, match="PROVIDER_INVALID_JSON"):
        client.get_json("geocoding", "/search/2/geocode/test.json", [])


def test_naive_departure_rejected_before_transport():
    spy = Spy(result(route()))
    with pytest.raises(ProviderError):
        TomTomAdapter(spy).routes(query(departure_at=NOW.replace(tzinfo=None)))
    assert not spy.calls


def test_truncated_response_is_sanitized_counted_and_not_retried(tmp_path):
    import http.client

    class Truncated(HttpOpener):
        def open(self, request, timeout):
            response = super().open(request, timeout)

            def broken_read(limit):
                raise http.client.IncompleteRead(b"private partial response", 10)

            response.read = broken_read
            return response

    opener = Truncated()
    budget = Gate2TomTomBudget(tmp_path / "budget.json")
    with pytest.raises(ProviderError, match="^PROVIDER_TRUNCATED_RESPONSE$"):
        TomTomHTTP("fake-private-key", budget, opener=opener).get_json(
            "routing", "/routing/1/calculateRoute/0,0:1,1/json", []
        )
    assert opener.calls == 1
    assert budget.read()["routing"] == 1


def test_explicit_seventh_routing_authorization_does_not_increase_geocoding(tmp_path):
    path = tmp_path / "budget.json"
    ordinary = Gate2TomTomBudget(path)
    for _ in range(6):
        with ordinary.claim("routing"):
            pass
        with ordinary.claim("geocoding"):
            pass
    authorized = Gate2TomTomBudget(path, approved_extra_routing_call=True)
    with authorized.claim("routing"):
        pass
    for budget, operation in (
        (authorized, "routing"),
        (authorized, "geocoding"),
        (ordinary, "routing"),
    ):
        with pytest.raises(ProviderError, match="MILESTONE_REQUEST_CAP"):
            with budget.claim(operation):
                pass
    assert authorized.read()["routing"] == 7 and authorized.read()["geocoding"] == 6


@pytest.mark.parametrize("counter", [-1, True, "0", 8])
def test_invalid_durable_budget_fails_before_network(tmp_path, counter):
    path = tmp_path / "budget.json"
    path.write_text(
        __import__("json").dumps({"routing": counter, "geocoding": 0, "stop_code": None})
    )
    opener = HttpOpener()
    with pytest.raises(ProviderError, match="BUDGET_STORAGE_INVALID"):
        TomTomHTTP("fake-private-key", Gate2TomTomBudget(path), opener=opener).get_json(
            "routing", "/routing/1/calculateRoute/0,0:1,1/json", []
        )
    assert opener.calls == 0
