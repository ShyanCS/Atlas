from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from atlas.domain import (
    POLICY_VERSION,
    DomainValidationError,
    RiskCheckpoint,
    RouteCandidate,
    WeatherObservation,
    evaluate_checkpoint,
    evaluate_route,
    integrate_exposure,
    meters_to_miles,
    miles_to_meters,
    rank_routes,
)
from atlas.domain import RiskLevel as R

DEPARTURE = datetime(2026, 10, 9, 19, tzinfo=timezone.utc)


def risk(level):
    if level is R.UNKNOWN:
        return evaluate_checkpoint(WeatherObservation(), D(0))
    wind = {R.LOW: 0, R.MODERATE: 25, R.HIGH: 35, R.SEVERE: 45, R.NO_TRAVEL: 55}[level]
    return evaluate_checkpoint(WeatherObservation(D(wind), D(0), D(0)), D(0))


def route(name, index, positions, levels, duration="100"):
    length = D(str(positions[-1]))
    duration = D(duration)
    points = tuple(
        RiskCheckpoint(
            D(str(position)),
            risk(level),
            DEPARTURE + timedelta(seconds=float(duration * D(str(position)) / length)),
            f"{name}-{i}",
        )
        for i, (position, level) in enumerate(zip(positions, levels))
    )
    return RouteCandidate(name, index, length, duration, points)


def test_midpoint_uneven_tail_conservation_and_weighted_mean():
    positions = [miles_to_meters(value) for value in [0, 25, 50, 65]]
    candidate = route("a", 0, positions, [R.LOW, R.HIGH, R.SEVERE, R.MODERATE])
    exposure = integrate_exposure(candidate.distance_m, candidate.checkpoints)
    assert [meters_to_miles(span.length_m) for span in exposure.spans] == list(
        map(D, ["12.5", "25", "20", "7.5"])
    )
    assert sum(exposure.distance_by_level_m.values()) == candidate.distance_m
    assert exposure.average_risk == D("117.5") / D(65) or abs(
        exposure.average_risk - D("117.5") / D(65)
    ) < D("1e-27")
    assert exposure.complete_fraction == 1


def test_unknown_categories_and_incomplete_no_travel_are_separate():
    proven = evaluate_checkpoint(WeatherObservation(D(55), None, None), D(0))
    candidate = route("a", 0, [0, 10, 20], [R.LOW, R.UNKNOWN, R.NO_TRAVEL])
    candidate = replace(
        candidate,
        checkpoints=candidate.checkpoints[:-1] + (replace(candidate.checkpoints[-1], risk=proven),),
    )
    result = evaluate_route(candidate)
    assert not result.eligible
    assert result.exposure.no_travel_m == 5
    assert result.exposure.unknown_m == 10
    assert result.exposure.incomplete_m == 15
    assert set(result.disqualification_reasons) == {"NO_TRAVEL", "INCOMPLETE_WEATHER"}
    assert sum(result.exposure.distance_by_level_m.values()) == 20


def test_all_unknown_average_is_absent_and_never_recommended():
    a = route("a", 0, [0, 10], [R.UNKNOWN, R.UNKNOWN])
    assert integrate_exposure(a.distance_m, a.checkpoints).average_risk is None
    assert rank_routes([a]).recommended_route_id is None


def test_severe_is_first_even_with_much_more_high_exposure():
    a = route("a", 0, [0, 10, 90, 100], [R.HIGH, R.HIGH, R.HIGH, R.SEVERE])
    b = route("b", 1, [0, 20, 80, 100], [R.LOW, R.LOW, R.LOW, R.SEVERE])
    assert rank_routes([b, a]).recommended_route_id == "a"


def test_high_is_second_before_mean_and_time():
    a = route("a", 0, [0, 10, 90, 100], [R.MODERATE, R.MODERATE, R.MODERATE, R.HIGH], "200")
    b = route("b", 1, [0, 20, 80, 100], [R.LOW, R.LOW, R.LOW, R.HIGH], "100")
    assert rank_routes([b, a]).recommended_route_id == "a"


def test_mean_is_third_and_duration_is_fourth():
    a = route("a", 0, [0, 100], [R.LOW, R.MODERATE], "200")
    b = route("b", 1, [0, 100], [R.MODERATE, R.MODERATE], "100")
    assert rank_routes([b, a]).recommended_route_id == "a"
    faster = replace(
        a,
        route_id="faster",
        candidate_index=2,
        duration_seconds=D("199.9999"),
        checkpoints=(
            a.checkpoints[0],
            replace(a.checkpoints[-1], eta_utc=DEPARTURE + timedelta(seconds=199.9999)),
        ),
    )
    assert rank_routes([a, faster]).recommended_route_id == "faster"


def test_ranking_uses_unrounded_exposure_and_original_index_exact_ties():
    a = route("z-random-id", 2, [0, D("99.9999998"), 100], [R.LOW, R.LOW, R.SEVERE])
    b = route("a-random-id", 0, [0, D("99.9999996"), 100], [R.LOW, R.LOW, R.SEVERE], "99")
    assert rank_routes([b, a]).recommended_route_id == "z-random-id"
    tied = replace(a, route_id="later-random-id", candidate_index=1)
    assert rank_routes([a, tied]).recommended_route_id == "later-random-id"
    assert rank_routes([a, tied]).policy_version == POLICY_VERSION


def test_all_blocked_never_promotes_least_unsafe_and_eligible_precedes_blocked():
    blocked = route("blocked", 0, [0, 100], [R.NO_TRAVEL, R.NO_TRAVEL])
    unknown = route("unknown", 1, [0, 100], [R.UNKNOWN, R.UNKNOWN])
    assert rank_routes([unknown, blocked]).recommended_route_id is None
    okay = route("okay", 2, [0, 100], [R.SEVERE, R.SEVERE])
    result = rank_routes([blocked, okay, unknown])
    assert result.recommended_route_id == "okay"
    assert [item.route.route_id for item in result.ordered_routes] == ["okay", "blocked", "unknown"]


@pytest.mark.parametrize("flag", ["routing_valid", "timing_valid", "geometry_valid"])
def test_route_quality_flags_are_eligibility_gates(flag):
    candidate = route("a", 0, [0, 10], [R.LOW, R.LOW])
    assert not evaluate_route(replace(candidate, **{flag: False})).eligible


def test_missing_naive_backwards_and_inconsistent_etas_are_ineligible():
    candidate = route("a", 0, [0, 10], [R.LOW, R.LOW])
    for eta in [
        None,
        datetime(2026, 10, 9),
        DEPARTURE - timedelta(seconds=1),
        DEPARTURE + timedelta(seconds=99),
    ]:
        bad = replace(
            candidate,
            checkpoints=(candidate.checkpoints[0], replace(candidate.checkpoints[1], eta_utc=eta)),
        )
        assert "TIMING_INVALID" in evaluate_route(bad).disqualification_reasons


@pytest.mark.parametrize("positions", [[1, 10], [0, 9], [0, 0, 10], [0, 11, 10]])
def test_invalid_endpoint_or_order_does_not_generate_exposure(positions):
    points = tuple(RiskCheckpoint(D(value), risk(R.LOW)) for value in positions)
    with pytest.raises(DomainValidationError):
        integrate_exposure(D(10), points)


def test_duplicate_indexes_are_rejected_and_empty_recommendation_is_safe():
    a = route("a", 0, [0, 10], [R.LOW, R.LOW])
    with pytest.raises(DomainValidationError):
        rank_routes([a, replace(a, route_id="b")])
    assert rank_routes([]).recommended_route_id is None


def test_unknown_cannot_be_promoted_by_a_contradictory_completeness_flag():
    candidate = route("a", 0, [0, 10], [R.UNKNOWN, R.UNKNOWN])
    malformed = replace(
        candidate,
        checkpoints=tuple(
            replace(point, risk=replace(point.risk, complete=True))
            for point in candidate.checkpoints
        ),
    )
    evaluation = evaluate_route(malformed)
    assert not evaluation.eligible and evaluation.exposure.complete_m == 0
    assert "INCOMPLETE_WEATHER" in evaluation.disqualification_reasons
    assert rank_routes([malformed]).recommended_route_id is None


def test_noncanonical_classification_is_rejected_before_exposure():
    candidate = route("a", 0, [0, 10], [R.LOW, R.LOW])
    malformed = tuple(
        replace(point, risk=replace(point.risk, level="unsafe-but-unknown"))
        for point in candidate.checkpoints
    )
    with pytest.raises(DomainValidationError):
        integrate_exposure(candidate.distance_m, malformed)
