from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from atlas.domain import (
    AccumulationForecast,
    AmbiguousLocalTimeError,
    DomainValidationError,
    InstantForecast,
    NonexistentLocalTimeError,
    match_hourly_accumulation,
    match_wind,
    resolve_local_departure,
)

T = datetime(2026, 10, 9, 19, tzinfo=timezone.utc)


def test_dst_spring_nonexistent_time_is_rejected():
    with pytest.raises(NonexistentLocalTimeError) as error:
        resolve_local_departure("2026-03-08T02:30:00", "America/New_York")
    assert error.value.code == "DEPARTURE_TIME_NONEXISTENT"


def test_dst_fall_requires_explicit_fold_and_maps_both_occurrences():
    with pytest.raises(AmbiguousLocalTimeError):
        resolve_local_departure("2026-11-01T01:30:00", "America/New_York")
    assert (
        resolve_local_departure("2026-11-01T01:30:00", "America/New_York", 0).isoformat()
        == "2026-11-01T05:30:00+00:00"
    )
    assert (
        resolve_local_departure("2026-11-01T01:30:00", "America/New_York", 1).isoformat()
        == "2026-11-01T06:30:00+00:00"
    )


def test_normal_cross_zone_and_non_hour_offset_departure():
    assert resolve_local_departure("2026-10-10T00:30:00", "Asia/Calcutta") == T
    assert resolve_local_departure("2026-10-09T15:00:00", "America/New_York") == T
    assert resolve_local_departure("2026-10-09T14:00:00", "America/Chicago") == T


@pytest.mark.parametrize(
    "local,zone,fold",
    [
        ("invalid", "UTC", None),
        (T, "UTC", None),
        ("2026-10-09T19:00", "Unknown/Zone", None),
        ("2026-10-09T19:00", "UTC", 2),
        ("2026-10-09T19:00", "UTC", True),
    ],
)
def test_invalid_local_departure_contract(local, zone, fold):
    with pytest.raises(DomainValidationError):
        resolve_local_departure(local, zone, fold)


def test_wind_nearest_hour_exact_tie_prefers_later_even_if_input_reversed():
    early = InstantForecast(T, D(10))
    late = InstantForecast(T + timedelta(hours=1), D(20))
    match = match_wind(T + timedelta(minutes=30), [late, early])
    assert match.sample == late and match.offset_seconds == 1800
    assert match_wind(T + timedelta(minutes=29), [late, early]).sample == early
    assert match_wind(T + timedelta(minutes=31), [early, late]).sample == late


def test_wind_missing_later_tie_is_not_replaced_by_earlier_valid_value():
    early = InstantForecast(T, D(10))
    late = InstantForecast(T + timedelta(hours=1), None)
    assert match_wind(T + timedelta(minutes=30), [early, late]) is None


def test_wind_no_horizon_fallback_coarse_or_synthetic_slot():
    assert (
        match_wind(T + timedelta(minutes=30, microseconds=1), [InstantForecast(T, D(10))]) is None
    )
    assert match_wind(T, [InstantForecast(T, D(10), 10800)]) is None
    assert match_wind(T, [InstantForecast(T, D(10), 3600, False)]) is None
    assert match_wind(T, []) is None


def test_wind_microsecond_tie_and_conflicting_duplicates():
    early = InstantForecast(T - timedelta(microseconds=1), D(10))
    late = InstantForecast(T + timedelta(microseconds=1), D(20))
    assert match_wind(T, [early, late]).sample == late
    assert match_wind(T, [InstantForecast(T, D(10)), InstantForecast(T, D(20))]) is None


def test_accumulation_start_open_end_closed_hour_boundaries():
    first = AccumulationForecast(T, T + timedelta(hours=1), D(".10"))
    second = AccumulationForecast(T + timedelta(hours=1), T + timedelta(hours=2), D(".25"))
    assert match_hourly_accumulation(T, [first, second]) is None
    assert match_hourly_accumulation(T + timedelta(hours=1), [first, second]) == first
    assert (
        match_hourly_accumulation(T + timedelta(hours=1, microseconds=1), [first, second]) == second
    )
    assert match_hourly_accumulation(T + timedelta(hours=2), [first, second]) == second


def test_accumulation_null_coarse_synthetic_missing_reference_never_zero():
    eta = T + timedelta(minutes=30)
    assert (
        match_hourly_accumulation(
            eta, [AccumulationForecast(T, T + timedelta(hours=6), D(6), 21600)]
        )
        is None
    )
    assert (
        match_hourly_accumulation(
            eta, [AccumulationForecast(T, T + timedelta(hours=1), D(1), 21600)]
        )
        is None
    )
    assert (
        match_hourly_accumulation(
            eta, [AccumulationForecast(T, T + timedelta(hours=1), D(1), 3600, False)]
        )
        is None
    )
    assert (
        match_hourly_accumulation(eta, [AccumulationForecast(T, T + timedelta(hours=1), None)])
        is None
    )
    assert match_hourly_accumulation(eta, []) is None


def test_accumulation_overlapping_or_conflicting_intervals_are_unavailable():
    first = AccumulationForecast(T, T + timedelta(hours=1), D(1))
    conflict = AccumulationForecast(T, T + timedelta(hours=1), D(2))
    shifted = AccumulationForecast(
        T + timedelta(minutes=15), T + timedelta(hours=1, minutes=15), D(1)
    )
    assert match_hourly_accumulation(T + timedelta(minutes=30), [first, conflict]) is None
    assert match_hourly_accumulation(T + timedelta(minutes=30), [first, shifted]) is None


def test_naive_forecast_timestamps_and_reversed_interval_are_rejected():
    with pytest.raises(DomainValidationError):
        match_wind(T, [InstantForecast(T.replace(tzinfo=None), D(1))])
    with pytest.raises(DomainValidationError):
        match_hourly_accumulation(T, [AccumulationForecast(T, T, D(1))])
