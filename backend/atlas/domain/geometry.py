"""WGS84 geometry mapped to native cumulative provider distances/timings."""

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from geographiclib.geodesic import Geodesic

from ._validation import DomainValidationError, require_decimal, utc_datetime
from .routes import METERS_PER_MILE


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self):
        for name, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180)):
            raw = getattr(self, name)
            if isinstance(raw, bool):
                raise DomainValidationError(f"Invalid {name}")
            try:
                value = float(raw)
            except (TypeError, ValueError, OverflowError):
                raise DomainValidationError(f"Invalid {name}") from None
            if not math.isfinite(value) or not lower <= value <= upper:
                raise DomainValidationError(f"Invalid {name}")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class ProgressAnchor:
    point_index: int
    distance_m: Decimal
    elapsed_seconds: Decimal


@dataclass(frozen=True)
class PlacedCheckpoint:
    distance_m: Decimal
    point: GeoPoint
    elapsed_seconds: Decimal
    eta_utc: datetime
    anchor_gap_m: Decimal
    anchor_gap_seconds: Decimal


def geodesic_distance_m(left: GeoPoint, right: GeoPoint):
    return Decimal(
        str(
            Geodesic.WGS84.Inverse(left.latitude, left.longitude, right.latitude, right.longitude)[
                "s12"
            ]
        )
    )


def sample_chainages(total_distance_m, interval_miles):
    total = require_decimal(total_distance_m, "total_distance_m", positive=True)
    if isinstance(interval_miles, bool) or interval_miles not in (10, 25, 50):
        raise DomainValidationError("Checkpoint interval must be 10, 25 or 50 miles")
    interval = Decimal(interval_miles) * METERS_PER_MILE
    result = [Decimal(0)]
    position = interval
    while position < total:
        result.append(position)
        position += interval
    result.append(total)
    return tuple(result)


@dataclass(frozen=True)
class RouteGeometry:
    points: tuple[GeoPoint, ...]
    anchors: tuple[ProgressAnchor, ...]
    geodesic_chainages_m: tuple[Decimal, ...]
    provider_chainages_m: tuple[Decimal, ...]

    @property
    def distance_m(self):
        return self.anchors[-1].distance_m

    def _bracket(self, distance_m):
        distance = require_decimal(distance_m, "checkpoint distance")
        if distance > self.distance_m:
            raise DomainValidationError("Checkpoint lies beyond route")
        index = bisect_left(tuple(anchor.distance_m for anchor in self.anchors), distance)
        right = max(1, index)
        return distance, self.anchors[right - 1], self.anchors[right]

    def point_at(self, distance_m):
        distance, left, right = self._bracket(distance_m)
        if distance == left.distance_m:
            return self.points[left.point_index]
        if distance == right.distance_m:
            return self.points[right.point_index]
        fraction = (distance - left.distance_m) / (right.distance_m - left.distance_m)
        start = self.geodesic_chainages_m[left.point_index]
        target = start + fraction * (self.geodesic_chainages_m[right.point_index] - start)
        index = bisect_left(
            self.geodesic_chainages_m, target, left.point_index, right.point_index + 1
        )
        if self.geodesic_chainages_m[index] == target:
            return self.points[index]
        a, b = self.points[index - 1], self.points[index]
        line = Geodesic.WGS84.Inverse(a.latitude, a.longitude, b.latitude, b.longitude)
        located = Geodesic.WGS84.Direct(
            a.latitude,
            a.longitude,
            line["azi1"],
            float(target - self.geodesic_chainages_m[index - 1]),
        )
        return GeoPoint(located["lat2"], located["lon2"])

    def elapsed_at(self, distance_m):
        distance, left, right = self._bracket(distance_m)
        fraction = (distance - left.distance_m) / (right.distance_m - left.distance_m)
        return left.elapsed_seconds + fraction * (right.elapsed_seconds - left.elapsed_seconds)

    def place(self, distance_m, departure_at):
        departure = utc_datetime(departure_at, "departure_at")
        distance, left, right = self._bracket(distance_m)
        elapsed = self.elapsed_at(distance)
        microseconds = int((elapsed * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))
        return PlacedCheckpoint(
            distance,
            self.point_at(distance),
            elapsed,
            departure + timedelta(microseconds=microseconds),
            right.distance_m - left.distance_m,
            right.elapsed_seconds - left.elapsed_seconds,
        )

    def slice(self, start_m, end_m):
        start = require_decimal(start_m, "slice start")
        end = require_decimal(end_m, "slice end")
        if end < start or end > self.distance_m:
            raise DomainValidationError("Invalid geometry slice bounds")
        if end == start:
            return (self.point_at(start),)
        middle = tuple(
            point
            for point, distance in zip(self.points, self.provider_chainages_m)
            if start < distance < end
        )
        values = (self.point_at(start),) + middle + (self.point_at(end),)
        return tuple(
            point for index, point in enumerate(values) if index == 0 or point != values[index - 1]
        )


def prepare_geometry(points, anchors):
    points, raw_anchors = tuple(points), tuple(anchors)
    if len(points) < 2 or any(not isinstance(point, GeoPoint) for point in points):
        raise DomainValidationError("At least two validated geographic points are required")
    if len(raw_anchors) < 2:
        raise DomainValidationError("Cumulative provider distance/time anchors are required")
    normalized = []
    for anchor in raw_anchors:
        if not isinstance(anchor, ProgressAnchor):
            raise DomainValidationError("A provider progress anchor is required")
        if (
            not isinstance(anchor.point_index, int)
            or isinstance(anchor.point_index, bool)
            or not 0 <= anchor.point_index < len(points)
        ):
            raise DomainValidationError("Invalid provider point index")
        normalized.append(
            ProgressAnchor(
                anchor.point_index,
                require_decimal(anchor.distance_m, "anchor distance"),
                require_decimal(anchor.elapsed_seconds, "anchor elapsed time"),
            )
        )
    anchors = tuple(normalized)
    if (
        anchors[0].point_index != 0
        or anchors[0].distance_m != 0
        or anchors[0].elapsed_seconds != 0
        or anchors[-1].point_index != len(points) - 1
        or anchors[-1].distance_m <= 0
        or anchors[-1].elapsed_seconds <= 0
    ):
        raise DomainValidationError(
            "Provider anchors must include complete distance/time endpoints"
        )
    if any(
        b.point_index <= a.point_index
        or b.distance_m <= a.distance_m
        or b.elapsed_seconds < a.elapsed_seconds
        for a, b in zip(anchors, anchors[1:])
    ):
        raise DomainValidationError(
            "Provider anchors must have increasing indexes/distances and monotonic time"
        )
    cumulative = [Decimal(0)]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + geodesic_distance_m(left, right))
    native = [Decimal(0)] * len(points)
    for left, right in zip(anchors, anchors[1:]):
        geodesic_length = cumulative[right.point_index] - cumulative[left.point_index]
        if geodesic_length <= 0:
            raise DomainValidationError(
                "Positive provider distance has no corresponding geometry length"
            )
        for index in range(left.point_index, right.point_index + 1):
            fraction = (cumulative[index] - cumulative[left.point_index]) / geodesic_length
            native[index] = left.distance_m + fraction * (right.distance_m - left.distance_m)
        native[right.point_index] = right.distance_m
    return RouteGeometry(points, anchors, tuple(cumulative), tuple(native))


def place_checkpoint(points, anchors, chainage_m, departure_at):
    return prepare_geometry(points, anchors).place(chainage_m, departure_at)


def slice_geometry(points, anchors, start_m, end_m):
    return prepare_geometry(points, anchors).slice(start_m, end_m)
