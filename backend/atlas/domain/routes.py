"""Exact midpoint exposure and eligibility-first lexicographic ordering."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction

from ._validation import DomainValidationError, require_decimal, utc_datetime
from .risk import ORDINALS, POLICY_VERSION, RiskLevel, RiskResult
from .temporal import timedelta_decimal_seconds

METERS_PER_MILE = Decimal("1609.344")


def miles_to_meters(value):
    return require_decimal(value, "miles") * METERS_PER_MILE


def meters_to_miles(value):
    with localcontext() as context:
        context.prec = 40
        return require_decimal(value, "meters") / METERS_PER_MILE


@dataclass(frozen=True)
class RiskCheckpoint:
    distance_m: Decimal
    risk: RiskResult
    eta_utc: datetime | None = None
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class RiskSpan:
    start_m: Decimal
    end_m: Decimal
    level: RiskLevel
    complete: bool
    checkpoint_index: int
    checkpoint_id: str | None = None

    @property
    def length_m(self):
        return self.end_m - self.start_m


@dataclass(frozen=True)
class Exposure:
    distance_m: Decimal
    low_m: Decimal
    moderate_m: Decimal
    high_m: Decimal
    severe_m: Decimal
    no_travel_m: Decimal
    unknown_m: Decimal
    complete_m: Decimal
    average_risk: Decimal | None
    spans: tuple[RiskSpan, ...]
    weighted_risk_sum: Decimal

    @property
    def incomplete_m(self):
        return self.distance_m - self.complete_m

    @property
    def classified_m(self):
        return self.distance_m - self.unknown_m

    @property
    def complete_fraction(self):
        return self.complete_m / self.distance_m

    @property
    def distance_by_level_m(self):
        return {
            RiskLevel.LOW: self.low_m,
            RiskLevel.MODERATE: self.moderate_m,
            RiskLevel.HIGH: self.high_m,
            RiskLevel.SEVERE: self.severe_m,
            RiskLevel.NO_TRAVEL: self.no_travel_m,
            RiskLevel.UNKNOWN: self.unknown_m,
        }

    @property
    def miles_by_level(self):
        return {level: meters_to_miles(value) for level, value in self.distance_by_level_m.items()}


@dataclass(frozen=True)
class RouteCandidate:
    route_id: str
    candidate_index: int
    distance_m: Decimal
    duration_seconds: Decimal
    checkpoints: tuple[RiskCheckpoint, ...]
    routing_valid: bool = True
    timing_valid: bool = True
    geometry_valid: bool = True

    def __post_init__(self):
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))


@dataclass(frozen=True)
class RouteEvaluation:
    route: RouteCandidate
    exposure: Exposure | None
    eligible: bool
    disqualification_reasons: tuple[str, ...]


@dataclass(frozen=True)
class Recommendation:
    recommended_route_id: str | None
    ordered_routes: tuple[RouteEvaluation, ...]
    policy_version: str = POLICY_VERSION


def integrate_exposure(distance_m, checkpoints) -> Exposure:
    length = require_decimal(distance_m, "distance_m", positive=True)
    checkpoints = tuple(checkpoints)
    if len(checkpoints) < 2:
        raise DomainValidationError("Origin and destination checkpoints are required")
    positions = tuple(
        require_decimal(point.distance_m, "checkpoint distance") for point in checkpoints
    )
    if positions[0] != 0 or positions[-1] != length:
        raise DomainValidationError("Checkpoints must include exact route endpoints")
    if any(right <= left for left, right in zip(positions, positions[1:])):
        raise DomainValidationError("Checkpoint distances must strictly increase")
    if any(not isinstance(point.risk, RiskResult) for point in checkpoints):
        raise DomainValidationError("A canonical risk result is required for each checkpoint")
    boundaries = (
        (Decimal(0),)
        + tuple((left + right) / 2 for left, right in zip(positions, positions[1:]))
        + (length,)
    )
    totals = {level: Decimal(0) for level in RiskLevel}
    complete = weighted = Decimal(0)
    spans = []
    for index, point in enumerate(checkpoints):
        if not isinstance(point.risk.level, RiskLevel):
            raise DomainValidationError(
                "Checkpoint classification must use the canonical risk enum"
            )
        span = RiskSpan(
            boundaries[index],
            boundaries[index + 1],
            point.risk.level,
            point.risk.complete and point.risk.level is not RiskLevel.UNKNOWN,
            index,
            point.checkpoint_id,
        )
        totals[span.level] += span.length_m
        if span.complete:
            complete += span.length_m
        if span.level in ORDINALS:
            weighted += span.length_m * ORDINALS[span.level]
        spans.append(span)
    classified = length - totals[RiskLevel.UNKNOWN]
    with localcontext() as context:
        context.prec = 40
        average = weighted / classified if classified else None
    return Exposure(
        length,
        totals[RiskLevel.LOW],
        totals[RiskLevel.MODERATE],
        totals[RiskLevel.HIGH],
        totals[RiskLevel.SEVERE],
        totals[RiskLevel.NO_TRAVEL],
        totals[RiskLevel.UNKNOWN],
        complete,
        average,
        tuple(spans),
        weighted,
    )


def evaluate_route(route: RouteCandidate) -> RouteEvaluation:
    reasons = []
    if not route.routing_valid:
        reasons.append("ROUTING_INVALID")
    if not route.geometry_valid:
        reasons.append("GEOMETRY_INVALID")
    timing_good = route.timing_valid
    try:
        duration = require_decimal(route.duration_seconds, "duration_seconds", positive=True)
        etas = tuple(utc_datetime(point.eta_utc, "checkpoint ETA") for point in route.checkpoints)
        if len(etas) < 2 or any(right < left for left, right in zip(etas, etas[1:])):
            timing_good = False
        elif abs(timedelta_decimal_seconds(etas[-1] - etas[0]) - duration) > Decimal("0.000001"):
            timing_good = False
    except DomainValidationError:
        timing_good = False
    if not timing_good:
        reasons.append("TIMING_INVALID")
    try:
        exposure = integrate_exposure(route.distance_m, route.checkpoints)
    except DomainValidationError:
        exposure = None
        if "GEOMETRY_INVALID" not in reasons:
            reasons.append("GEOMETRY_INVALID")
    if any(
        isinstance(point.risk, RiskResult) and point.risk.level is RiskLevel.NO_TRAVEL
        for point in route.checkpoints
    ):
        reasons.append("NO_TRAVEL")
    if not route.checkpoints or any(
        not isinstance(point.risk, RiskResult)
        or not point.risk.complete
        or point.risk.level is RiskLevel.UNKNOWN
        for point in route.checkpoints
    ):
        reasons.append("INCOMPLETE_WEATHER")
    return RouteEvaluation(route, exposure, not reasons, tuple(reasons))


def rank_routes(candidates) -> Recommendation:
    candidates = tuple(candidates)
    if any(
        not isinstance(route.candidate_index, int)
        or isinstance(route.candidate_index, bool)
        or route.candidate_index < 0
        for route in candidates
    ):
        raise DomainValidationError("candidate_index must be a nonnegative immutable integer")
    if len({route.candidate_index for route in candidates}) != len(candidates):
        raise DomainValidationError("Candidate indexes must be unique")
    if len({route.route_id for route in candidates}) != len(candidates):
        raise DomainValidationError("Candidate route IDs must be unique")
    if any(
        not isinstance(route.route_id, str) or not route.route_id.strip() for route in candidates
    ):
        raise DomainValidationError("Candidate route IDs must be nonempty strings")
    evaluated = tuple(evaluate_route(route) for route in candidates)

    def key(item):
        exposure = item.exposure
        # Exact rational comparison avoids both display rounding and repeating-Decimal truncation.
        mean = Fraction(exposure.weighted_risk_sum) / Fraction(exposure.classified_m)
        return (
            exposure.severe_m,
            exposure.high_m,
            mean,
            require_decimal(item.route.duration_seconds, "duration_seconds"),
            item.route.candidate_index,
        )

    eligible = tuple(sorted((item for item in evaluated if item.eligible), key=key))
    blocked = tuple(
        sorted(
            (item for item in evaluated if not item.eligible),
            key=lambda item: item.route.candidate_index,
        )
    )
    return Recommendation(eligible[0].route.route_id if eligible else None, eligible + blocked)
