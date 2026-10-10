from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from atlas.domain import (
    DomainValidationError,
    GeoPoint,
    ProgressAnchor,
    geodesic_distance_m,
    miles_to_meters,
    place_checkpoint,
    prepare_geometry,
    sample_chainages,
    slice_geometry,
)

DEPARTURE = datetime(2026, 10, 9, 19, 39, 33, tzinfo=timezone.utc)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_exact_chainages_start_finish_and_endpoint_dedup(interval):
    total = miles_to_meters(interval * 2)
    assert sample_chainages(total, interval) == (D(0), miles_to_meters(interval), total)
    short = miles_to_meters(1)
    assert sample_chainages(short, interval) == (D(0), short)


def test_uneven_tail_positions_are_native_route_distance():
    assert sample_chainages(miles_to_meters(65), 25) == tuple(
        miles_to_meters(v) for v in [0, 25, 50, 65]
    )


@pytest.mark.parametrize(
    "total,interval", [(0, 10), (-1, 25), (D("NaN"), 10), (100, 1), (100, True)]
)
def test_invalid_sampling_inputs(total, interval):
    with pytest.raises(DomainValidationError):
        sample_chainages(total, interval)


def test_provider_piecewise_timing_is_not_whole_route_constant_speed():
    points = (GeoPoint(0, 0), GeoPoint(0, 1), GeoPoint(0, 2))
    anchors = (
        ProgressAnchor(0, D(0), D(0)),
        ProgressAnchor(1, D(1000), D(90)),
        ProgressAnchor(2, D(2000), D(100)),
    )
    geometry = prepare_geometry(points, anchors)
    checkpoint = geometry.place(D(1000), DEPARTURE)
    assert checkpoint.elapsed_seconds == 90
    assert checkpoint.point == points[1]
    assert checkpoint.eta_utc.isoformat() == "2026-10-09T19:41:03+00:00"
    assert geometry.elapsed_at(D(1500)) == 95
    assert geometry.elapsed_at(D(2000)) == 100
    assert abs(geometry.point_at(D(500)).longitude - 0.5) < 1e-10


def test_geometry_uses_distance_inside_anchor_not_point_count():
    points = (GeoPoint(0, 0), GeoPoint(0, 0.1), GeoPoint(0, 1))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(2, D(1000), D(100)))
    geometry = prepare_geometry(points, anchors)
    assert abs(geometry.point_at(D(500)).longitude - 0.5) < 1e-10
    assert abs(geometry.provider_chainages_m[1] - D(100)) < D("1e-10")


def test_geospatial_loop_and_slice_preserve_route_order():
    points = (GeoPoint(0, 0), GeoPoint(0, 1), GeoPoint(1, 1), GeoPoint(0, 0))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(3, D(1000), D(100)))
    geometry = prepare_geometry(points, anchors)
    assert geometry.point_at(0) == geometry.point_at(1000) == points[0]
    assert geometry.slice(0, 1000) == points
    sliced = geometry.slice(250, 750)
    assert sliced[0] == geometry.point_at(250) and sliced[-1] == geometry.point_at(750)
    assert geometry.geodesic_chainages_m[-1] > 0
    assert slice_geometry(points, anchors, 0, 1000) == points


def test_duplicate_geometry_points_are_allowed_inside_real_positive_span():
    points = (GeoPoint(0, 0), GeoPoint(0, 0), GeoPoint(0, 1))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(2, D(1000), D(100)))
    geometry = prepare_geometry(points, anchors)
    assert abs(geometry.point_at(500).longitude - 0.5) < 1e-10
    assert geometry.slice(0, 1000) == (points[0], points[-1])


def test_wgs84_antimeridian_position_does_not_cross_greenwich():
    points = (GeoPoint(10, 179), GeoPoint(10, -179))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(1, D(1000), D(100)))
    midpoint = prepare_geometry(points, anchors).point_at(500)
    assert abs(abs(midpoint.longitude) - 180) < 1e-8
    assert midpoint.latitude > 10
    assert D("200000") < geodesic_distance_m(*points) < D("230000")


@pytest.mark.parametrize(
    "lat,lon", [(91, 0), (0, 181), (float("nan"), 0), (0, float("inf")), (True, 0), ("bad", 0)]
)
def test_invalid_coordinates(lat, lon):
    with pytest.raises(DomainValidationError):
        GeoPoint(lat, lon)


def test_missing_bad_or_nonmonotonic_anchors_do_not_fall_back():
    points = (GeoPoint(0, 0), GeoPoint(0, 1), GeoPoint(0, 2))
    bad_sets = [
        (),
        (ProgressAnchor(0, D(0), D(0)),),
        (ProgressAnchor(0, D(1), D(0)), ProgressAnchor(2, D(1000), D(100))),
        (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(1, D(1000), D(100))),
        (
            ProgressAnchor(0, D(0), D(0)),
            ProgressAnchor(1, D(1000), D(100)),
            ProgressAnchor(2, D(2000), D(90)),
        ),
        (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(2, D(0), D(100))),
        (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(True, D(1000), D(100))),
    ]
    for anchors in bad_sets:
        with pytest.raises(DomainValidationError):
            prepare_geometry(points, anchors)


def test_geometry_rejects_impossible_distance_and_aware_departure_is_required():
    identical = (GeoPoint(0, 0), GeoPoint(0, 0))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(1, D(1000), D(100)))
    with pytest.raises(DomainValidationError):
        prepare_geometry(identical, anchors)
    points = (GeoPoint(0, 0), GeoPoint(0, 1))
    with pytest.raises(DomainValidationError):
        place_checkpoint(points, anchors, 500, datetime(2026, 10, 9))
    geometry = prepare_geometry(points, anchors)
    for bad in [-1, 1001, D("NaN")]:
        with pytest.raises(DomainValidationError):
            geometry.point_at(bad)
    with pytest.raises(DomainValidationError):
        geometry.slice(700, 200)


def test_subsecond_eta_rounding_is_explicit_microsecond_precision():
    points = (GeoPoint(0, 0), GeoPoint(0, 1))
    anchors = (ProgressAnchor(0, D(0), D(0)), ProgressAnchor(1, D(3), D(1)))
    checkpoint = place_checkpoint(points, anchors, 1, DEPARTURE)
    assert checkpoint.elapsed_seconds == D(1) / D(3)
    assert checkpoint.eta_utc.microsecond == 333333
