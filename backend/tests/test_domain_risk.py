from dataclasses import FrozenInstanceError
from decimal import Decimal as D

import pytest

from atlas.domain import (
    DomainValidationError,
    WeatherObservation,
    classify_rain,
    classify_snow,
    classify_wind,
    evaluate_checkpoint,
    explain_checkpoint,
)
from atlas.domain import RiskLevel as R


@pytest.mark.parametrize(
    "value,level",
    [
        ("0", R.LOW),
        ("24.999999", R.LOW),
        ("25", R.MODERATE),
        ("25.000001", R.MODERATE),
        ("34.999999", R.MODERATE),
        ("35", R.HIGH),
        ("35.000001", R.HIGH),
        ("44.999999", R.HIGH),
        ("45", R.SEVERE),
        ("45.000001", R.SEVERE),
        ("54.999999", R.SEVERE),
        ("55", R.NO_TRAVEL),
        ("55.000001", R.NO_TRAVEL),
    ],
)
def test_exact_wind_boundaries(value, level):
    assert classify_wind(D(value), D("30000")) is level


@pytest.mark.parametrize(
    "classifier,values",
    [
        (
            classify_rain,
            [
                (".099999", R.LOW),
                (".10", R.MODERATE),
                (".100001", R.MODERATE),
                (".249999", R.MODERATE),
                (".25", R.HIGH),
                (".250001", R.HIGH),
                (".499999", R.HIGH),
                (".50", R.SEVERE),
                (".500001", R.SEVERE),
                (".999999", R.SEVERE),
                ("1.00", R.SEVERE),
                ("1.000001", R.NO_TRAVEL),
            ],
        ),
        (
            classify_snow,
            [
                (".499999", R.LOW),
                (".5", R.MODERATE),
                (".500001", R.MODERATE),
                (".999999", R.MODERATE),
                ("1", R.HIGH),
                ("1.000001", R.HIGH),
                ("1.999999", R.HIGH),
                ("2", R.SEVERE),
                ("2.000001", R.SEVERE),
                ("2.999999", R.SEVERE),
                ("3", R.SEVERE),
                ("3.000001", R.NO_TRAVEL),
            ],
        ),
    ],
)
def test_precipitation_boundaries(classifier, values):
    for value, level in values:
        assert classifier(D(value)) is level


@pytest.mark.parametrize(
    "wind,cargo,level",
    [
        ("45", "30000", R.SEVERE),
        ("45", "30000.000001", R.NO_TRAVEL),
        ("54.999999", "30000.01", R.NO_TRAVEL),
        ("35", "40000", R.HIGH),
        ("35", "40000.000001", R.SEVERE),
        ("44.999999", "40000.01", R.SEVERE),
        ("34.999999", "90000", R.MODERATE),
        ("55", "0", R.NO_TRAVEL),
        ("55", "30000", R.NO_TRAVEL),
        ("55", "100000.1", R.NO_TRAVEL),
    ],
)
def test_strict_cargo_overrides(wind, cargo, level):
    assert classify_wind(D(wind), D(cargo)) is level


@pytest.mark.parametrize(
    "invalid", [None, "garbage", "", D("NaN"), D("Infinity"), -1, True, {}, []]
)
def test_invalid_measurements_never_become_low(invalid):
    assert classify_wind(invalid, D(0)) is R.UNKNOWN
    assert classify_rain(invalid) is R.UNKNOWN
    assert classify_snow(invalid) is R.UNKNOWN


@pytest.mark.parametrize("invalid", [None, "bad", D("NaN"), D("Infinity"), -1, False])
def test_invalid_required_cargo_is_rejected(invalid):
    with pytest.raises(DomainValidationError):
        evaluate_checkpoint(WeatherObservation(D(55), D(0), D(0)), invalid)


def test_maximum_condition_and_governing_ties():
    result = evaluate_checkpoint(WeatherObservation(D(45), D(".5"), D(2)), D(0))
    assert result.level is R.SEVERE and result.complete
    assert result.governing_conditions == ("wind", "rain", "snow")
    assert result.rule_ids == ("wind.severe", "rain.severe", "snow.severe")


def test_partial_high_retains_lower_bound_but_is_unknown():
    result = evaluate_checkpoint(WeatherObservation(D(35), D(0), None), D(0))
    assert result.level is R.UNKNOWN and not result.complete
    assert result.known_lower_bound is R.HIGH
    assert result.missing_conditions == ("snow",)
    assert result.governing_conditions == ("wind",)


def test_known_no_travel_keeps_incomplete_flags_and_override_reason():
    result = evaluate_checkpoint(WeatherObservation(D(45), None, None), D("30000.01"))
    assert result.level is R.NO_TRAVEL and not result.complete
    assert result.rule_ids == ("wind.cargo_gt_30000.no_travel",)
    assert result.missing_conditions == ("rain", "snow")


def test_all_missing_has_no_numeric_lower_bound_and_zero_is_complete():
    missing = evaluate_checkpoint(WeatherObservation(), D(0))
    assert missing.level is R.UNKNOWN and missing.known_lower_bound is None
    zero = evaluate_checkpoint(WeatherObservation(D(0), D(0), D(0)), D(0))
    assert zero.level is R.LOW and zero.complete
    with pytest.raises(FrozenInstanceError):
        zero.complete = False


def test_explanation_preserves_exact_values_and_half_open_rain_boundary():
    weather = WeatherObservation(D("34.999999999999"), D(".25"), D("3"))
    text = " ".join(explain_checkpoint(weather, D("30000")))
    assert "34.999999999999 mph" in text
    assert "0.25 <= rain < 0.50" in text and "2.0 <= new snowfall <= 3.0" in text
    assert "Overall Severe" in text and "governing snow" in text


@pytest.mark.parametrize(
    "wind,cargo,expected",
    [
        ("45", "30000", "not activated at or below 30,000"),
        ("45", "30000.01", "cargo > 30,000 lb (strict) => No Travel"),
        ("35", "40000", "not activated at or below 40,000"),
        ("35", "40000.01", "cargo > 40,000 lb (strict) => Severe"),
        ("55", "0", "for any cargo load => No Travel"),
    ],
)
def test_explanations_describe_strict_cargo_overrides(wind, cargo, expected):
    text = " ".join(explain_checkpoint(WeatherObservation(D(wind), D(0), D(0)), D(cargo)))
    assert expected in text


def test_explanation_distinguishes_proven_no_travel_from_unknown_lower_bound():
    blocked = " ".join(explain_checkpoint(WeatherObservation(D(55), None, None), D(0)))
    assert "Overall No Travel" in blocked and "coverage remains incomplete" in blocked
    partial = " ".join(explain_checkpoint(WeatherObservation(D(35), D(0), None), D(0)))
    assert "Overall Unknown" in partial and "Known lower bound: High" in partial


def test_explanation_rejects_mismatched_precomputed_risk():
    low = WeatherObservation(D(0), D(0), D(0))
    high = evaluate_checkpoint(WeatherObservation(D(35), D(0), D(0)), D(0))
    with pytest.raises(DomainValidationError):
        explain_checkpoint(low, D(0), high)
