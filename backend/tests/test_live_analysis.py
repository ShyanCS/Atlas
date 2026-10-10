"""Full authored-adapter orchestration; original domain/sample tests retained."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from atlas.domain import GeoPoint, ProgressAnchor
from atlas.models import AnalysisSnapshot
from atlas.providers.interfaces import NormalizedRoute
from atlas.providers.open_meteo import OpenMeteoAdapter
from atlas.providers.tomtom import RoutingResult
from atlas.providers.tomtom_http import ProviderError
from atlas.services.live import LiveBundle, create_live_analysis, live_frame

pytestmark = pytest.mark.django_db


def inputs():
    return {
        "mode": "live",
        "scenario": "complete",
        "origin": {"name": "Authored A", "latitude": 40, "longitude": -90},
        "destination": {"name": "Authored B", "latitude": 40, "longitude": -89},
        "departure_at": timezone.now().replace(microsecond=0) + timedelta(hours=1),
        "origin_timezone": "America/Chicago",
        "load_weight_lb": Decimal(24000),
        "checkpoint_interval_miles": 25,
    }


class Routes:
    def __init__(self, count=3, valid=True):
        self.count, self.valid = count, valid

    def route_candidates(self, query):
        routes = tuple(
            NormalizedRoute(
                f"authored-{i}",
                f"Authored {i}",
                (query.origin, GeoPoint(40 + i * 0.1, -89.5), query.destination),
                (
                    ProgressAnchor(0, Decimal(0), Decimal(0)),
                    ProgressAnchor(1, Decimal(50000), Decimal(1800)),
                    ProgressAnchor(2, Decimal(100000), Decimal(3600)),
                ),
                Decimal(100000),
                Decimal(3600),
                candidate_index=i,
                departure_at=query.departure_at,
                arrival_at=query.departure_at + timedelta(hours=1),
                geometry_valid=True,
                timing_valid=True,
                routing_valid=self.valid,
            )
            for i in range(self.count)
        )
        return RoutingResult(routes, (), 3, self.count)


class JSONWeather:
    def __init__(self, missing=False):
        self.missing = missing

    def get_json(self, parameters):
        from datetime import datetime
        from datetime import timezone as tz

        p = dict(parameters)
        start = datetime.fromisoformat(p["start_hour"]).replace(tzinfo=tz.utc)
        end = datetime.fromisoformat(p["end_hour"]).replace(tzinfo=tz.utc)
        times = [
            int((start + timedelta(hours=i)).timestamp())
            for i in range(int((end - start).total_seconds() / 3600) + 1)
        ]
        return [
            {
                "latitude": float(lat),
                "longitude": float(lon),
                "utc_offset_seconds": 0,
                "hourly_units": {
                    "wind_speed_10m": "mp/h",
                    "rain": "inch",
                    "showers": "inch",
                    "snowfall": "inch",
                },
                "hourly": {
                    "time": times,
                    "wind_speed_10m": [20] * len(times),
                    "rain": [0] * len(times),
                    "showers": [0] * len(times),
                    "snowfall": [None if self.missing else 0] * len(times),
                },
            }
            for lat, lon in zip(p["latitude"].split(","), p["longitude"].split(","))
        ]


@override_settings(
    ATLAS_LIVE_ENABLED=True,
    ATLAS_NONCOMMERCIAL_ASSESSMENT=True,
    ATLAS_ACCEPT_PROVIDER_SNOWFALL=True,
    ATLAS_TOMTOM_KEY="authored-not-a-key",
)
@pytest.mark.parametrize(
    "missing,valid,state",
    [(False, True, "recommended"), (True, True, "unverified"), (False, False, "unverified")],
)
def test_live_snapshot_and_all_49_frames_share_identity_immutable_ranking(
    monkeypatch, missing, valid, state
):
    monkeypatch.setattr(
        "atlas.services.live.providers",
        lambda: (
            Routes(valid=valid),
            OpenMeteoAdapter(JSONWeather(missing), accept_provider_snowfall=True),
        ),
    )
    snapshot = create_live_analysis(inputs())
    assert snapshot.result["sample_data"] is False and snapshot.result["mode"] == "live"
    assert snapshot.result["recommendation"]["state"] == state
    assert len(snapshot.result["routes"]) == 3
    before = snapshot.result.copy()
    for hour in range(49):
        for variable in ("wind", "rain", "snow"):
            frame = live_frame(snapshot, hour, variable)
            assert frame["analysis_id"] == str(snapshot.id) and frame["hour"] == hour
            assert not frame["sample_data"]
    snapshot.refresh_from_db()
    assert before == snapshot.result
    if state == "recommended":
        assert all(r["eligible"] for r in snapshot.result["routes"])


def test_fewer_candidates_disclosed_never_invented():
    bundle = LiveBundle(
        inputs(), Routes(count=2), OpenMeteoAdapter(JSONWeather(), accept_provider_snowfall=True)
    )
    assert len(bundle.fixtures) == 2
    assert any("THREE_ROUTE_REQUIREMENT_NOT_MET" in warning for warning in bundle.warnings)


def test_disabled_live_mode_no_network_or_snapshot():
    response = APIClient().post("/api/v1/analyses/", {"mode": "live"}, format="json")
    assert response.status_code == 503
    assert not AnalysisSnapshot.objects.exists()


@override_settings(
    ATLAS_LIVE_ENABLED=True,
    ATLAS_NONCOMMERCIAL_ASSESSMENT=True,
    ATLAS_ACCEPT_PROVIDER_SNOWFALL=True,
    ATLAS_TOMTOM_KEY="authored-not-a-key",
)
def test_live_api_schema_serialization_and_failure_never_sample_substitution(monkeypatch):
    monkeypatch.setattr(
        "atlas.services.live.providers",
        lambda: (Routes(), OpenMeteoAdapter(JSONWeather(), accept_provider_snowfall=True)),
    )
    data = inputs()
    data["departure_at"] = data["departure_at"].isoformat()
    response = APIClient().post("/api/v1/analyses/", data, format="json")
    assert response.status_code == 201, response.data
    assert (
        response.data["routes"][0]["checkpoints"][0]["measurements"]["rain"]["provenance"][
            "model_run_at"
        ]
        is None
    )
    frame = APIClient().get(f"/api/v1/analyses/{response.data['id']}/frames/?hour=48&variable=snow")
    assert frame.status_code == 200 and frame.data["mode"] == "live"

    def fail():
        raise ProviderError("WEATHER_QUOTA", status=429)

    monkeypatch.setattr("atlas.services.live.providers", fail)
    response = APIClient().post("/api/v1/analyses/", data, format="json")
    assert response.status_code == 429 and response.data["error"]["code"] == "WEATHER_QUOTA"


@override_settings(
    ATLAS_LIVE_ENABLED=True,
    ATLAS_NONCOMMERCIAL_ASSESSMENT=True,
    ATLAS_ACCEPT_PROVIDER_SNOWFALL=True,
    ATLAS_TOMTOM_KEY="authored-not-a-key",
)
def test_past_departure_rejected_before_provider(monkeypatch):
    def fail():
        pytest.fail("No provider request allowed for a past departure")

    monkeypatch.setattr("atlas.services.live.providers", fail)
    data = inputs()
    data["departure_at"] = timezone.now() - timedelta(hours=1)
    with pytest.raises(Exception, match="Live assessment departure"):
        create_live_analysis(data)
