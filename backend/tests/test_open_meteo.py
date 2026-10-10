"""Authored JSON, never private provider payloads. Numerical/source boundary tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.domain import GeoPoint
from atlas.providers.assessment_http import AssessmentBudget
from atlas.providers.interfaces import WeatherQuery
from atlas.providers.open_meteo import OpenMeteoAdapter, select_measurements
from atlas.providers.tomtom_http import ProviderError

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def payload():
    return {
        "latitude": 40,
        "longitude": -90,
        "utc_offset_seconds": 0,
        "hourly_units": {
            "wind_speed_10m": "mp/h",
            "rain": "inch",
            "showers": "inch",
            "snowfall": "inch",
        },
        "hourly": {
            "time": [int((NOW + timedelta(hours=i)).timestamp()) for i in range(3)],
            "wind_speed_10m": [20, 40, 60],
            "rain": [0, Decimal(".10"), Decimal(".25")],
            "showers": [0, Decimal(".05"), Decimal(".2")],
            "snowfall": [0, 1, 2],
        },
    }


class Transport:
    def __init__(self, raw=None):
        self.raw = raw if raw is not None else payload()
        self.requests = []

    def get_json(self, parameters):
        self.requests.append(dict(parameters))
        return self.raw


def acquire(raw=None, snow=True):
    return OpenMeteoAdapter(Transport(raw), accept_provider_snowfall=snow).measurements(
        WeatherQuery((GeoPoint(40, -90),), NOW, NOW + timedelta(hours=2))
    )


def test_actual_quantity_contract_liquid_components_and_snow_disclosure():
    records = acquire()
    values, measurements = select_measurements(records, NOW + timedelta(minutes=40))
    assert values == {"wind": Decimal(40), "rain": Decimal(".15"), "snow": Decimal(1)}
    assert measurements["rain"]["provenance"]["interval_start"] == "2026-10-10T12:00:00Z"
    assert measurements["rain"]["provenance"]["interval_end"] == "2026-10-10T13:00:00Z"
    assert all(m.provenance["model_run_at"] is None and not m.provenance["native"] for m in records)
    assert (
        "PROVIDER_SNOWFALL_FIXED_7_TO_1_RELATIONSHIP"
        in measurements["snow"]["provenance"]["quality_flags"]
    )


def test_exact_hour_uses_preceding_interval_wind_half_tie_later():
    records = acquire()
    assert select_measurements(records, NOW + timedelta(hours=1))[0]["rain"] == Decimal(".15")
    assert select_measurements(records, NOW + timedelta(minutes=30))[0]["wind"] == 40


@pytest.mark.parametrize("variable", ["rain", "showers", "snowfall", "wind_speed_10m"])
@pytest.mark.parametrize("missing", [None, -1, True, "NaN"])
def test_missing_invalid_never_zero_or_temperature_phase_inference(variable, missing):
    raw = payload()
    raw["hourly"][variable][1] = missing
    values, measurements = select_measurements(acquire(raw), NOW + timedelta(minutes=40))
    target = (
        "rain" if variable in {"rain", "showers"} else "snow" if variable == "snowfall" else "wind"
    )
    assert values[target] is None
    assert measurements[target]["missing_reason"] == "PROVIDER_VALUE_MISSING_OR_INVALID"


def test_valid_zero_independent_of_missing_and_no_snow_approval():
    values, _ = select_measurements(acquire(), NOW)
    assert values["rain"] == values["snow"] == 0
    values, result = select_measurements(acquire(snow=False), NOW)
    assert (
        values["snow"] is None
        and result["snow"]["missing_reason"] == "PROVIDER_SNOWFALL_NOT_APPROVED"
    )


@pytest.mark.parametrize(
    "defect",
    [
        "unit",
        "offset",
        "gap",
        "duplicate",
        "length",
        "missing_field",
        "fractional_epoch",
        "nonhour",
    ],
)
def test_incompatible_contract_rejected(defect):
    raw = payload()
    if defect == "unit":
        raw["hourly_units"]["rain"] = "mm"
    if defect == "offset":
        raw["utc_offset_seconds"] = 3600
    if defect == "gap":
        raw["hourly"]["time"][1] += 3600
    if defect == "duplicate":
        raw["hourly"]["time"][1] = raw["hourly"]["time"][0]
    if defect == "length":
        raw["hourly"]["snowfall"].pop()
    if defect == "missing_field":
        raw["hourly"].pop("showers")
    if defect == "fractional_epoch":
        raw["hourly"]["time"][0] += 0.5
    if defect == "nonhour":
        raw["hourly"]["time"] = [t + 60 for t in raw["hourly"]["time"]]
    with pytest.raises(ProviderError, match="WEATHER_CONTRACT_INVALID"):
        acquire(raw)


def test_outside_time_window_unknown_with_null_source_instant():
    values, result = select_measurements(acquire(), NOW + timedelta(days=1))
    assert all(v is None for v in values.values())
    assert all(m["provenance"]["valid_at"] is None for m in result.values())


@pytest.mark.parametrize("defect", ["distant", "invalid", "wrong_index"])
def test_source_coordinate_and_location_order_rejected(defect):
    raw = payload()
    if defect == "distant":
        raw["latitude"] = 45
    elif defect == "invalid":
        raw["latitude"] = 100
    else:
        raw["location_id"] = 1
    with pytest.raises(ProviderError, match="WEATHER_CONTRACT_INVALID"):
        acquire(raw)


def test_batch_cardinality_and_limit():
    with pytest.raises(ProviderError, match="WEATHER_LOCATION_COUNT_MISMATCH"):
        acquire([payload(), payload()])
    with pytest.raises(ProviderError, match="WEATHER_BATCH_LIMIT"):
        OpenMeteoAdapter(Transport()).measurements(
            WeatherQuery(tuple(GeoPoint(40, -90) for _ in range(21)), NOW, NOW + timedelta(hours=1))
        )


def test_budget_debits_failed_calls_and_latches_quota_without_retry(tmp_path):
    budget = AssessmentBudget(tmp_path / "budget.json", {"weather": 2})
    with pytest.raises(ProviderError):
        with budget.claim("weather"):
            raise ProviderError("WEATHER_QUOTA", status=429)
    with pytest.raises(ProviderError, match="WEATHER_QUOTA"):
        with budget.claim("weather"):
            pytest.fail("Quota stop must prevent new I/O")


def test_budget_durable_cap_never_auto_resets(tmp_path):
    path = tmp_path / "budget.json"
    with AssessmentBudget(path, {"weather": 1}).claim("weather"):
        pass
    with pytest.raises(ProviderError, match="ASSESSMENT_REQUEST_CAP"):
        with AssessmentBudget(path, {"weather": 1}).claim("weather"):
            pytest.fail("Cap must prevent I/O")
