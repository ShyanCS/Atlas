"""Bounded local live assessment orchestration, sharing the unmodified risk engine.

No raw provider payload retention, sample substitution, native decoder or jobs.
Forecast scalar slots are acquired once for checkpoint points and reused by the
49-position viewer. Viewer bins are geographic samples, not native model cells.
"""

from datetime import datetime, timedelta
from threading import Lock

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from atlas.api.errors import AtlasError
from atlas.domain import GeoPoint, prepare_geometry, sample_chainages
from atlas.models import AnalysisSnapshot
from atlas.providers.assessment_http import AssessmentBudget, OpenMeteoHTTP, https_opener
from atlas.providers.interfaces import RoutingQuery, WeatherQuery
from atlas.providers.open_meteo import (
    SOURCE_POLICY,
    OpenMeteoAdapter,
    point_key,
    select_measurements,
)
from atlas.providers.tomtom import TomTomAdapter
from atlas.providers.tomtom_http import ProviderError, TomTomHTTP
from atlas.services.analysis import ADMISSION_LOCK, build_result, coordinate, iso, number

LIVE_VERSION = "assessment-json-v1"
LIVE_LOCK = Lock()


def live_available():
    return bool(
        settings.ATLAS_LIVE_ENABLED
        and settings.ATLAS_NONCOMMERCIAL_ASSESSMENT
        and settings.ATLAS_ACCEPT_PROVIDER_SNOWFALL
        and settings.ATLAS_TOMTOM_KEY
        and (
            not settings.ATLAS_HOSTED
            or (settings.ATLAS_PUBLIC_WEATHER_CONFIRMED and settings.ATLAS_PUBLIC_TOMTOM_CONFIRMED)
        )
    )


def require_live():
    if not live_available():
        raise AtlasError(
            "LIVE_MODE_UNAVAILABLE",
            "Route planning is not enabled on this deployment. You can explore the example trip."
            if settings.ATLAS_HOSTED
            else "Enable the explicitly noncommercial assessment source policy and server-side routing key to use live mode.",
            status=503,
        )


def providers():
    require_live()
    from django.db import connection

    from atlas.providers.assessment_http import DeadlineBudget
    from atlas.providers.database_budget import DatabaseAssessmentBudget

    budget = DeadlineBudget(
        DatabaseAssessmentBudget()
        if connection.vendor == "postgresql"
        else AssessmentBudget(settings.ATLAS_PROVIDER_BUDGET_PATH),
        settings.ATLAS_ACQUISITION_SECONDS,
    )
    opener = https_opener(settings.ATLAS_CA_BUNDLE)
    return (
        TomTomAdapter(
            TomTomHTTP(
                settings.ATLAS_TOMTOM_KEY,
                budget,
                opener=opener,
                timeout_seconds=settings.ATLAS_PROVIDER_TIMEOUT_SECONDS,
            )
        ),
        OpenMeteoAdapter(
            OpenMeteoHTTP(
                budget, opener=opener, timeout_seconds=settings.ATLAS_PROVIDER_TIMEOUT_SECONDS
            ),
            accept_provider_snowfall=True,
        ),
    )


def provider_failure(error):
    raise AtlasError(
        error.code,
        "The live provider request could not be completed. No synthetic data was substituted. Check the server allowance or selected endpoints before trying again.",
        status=429 if error.status == 429 or "CAP" in error.code else 503,
        details=getattr(error, "diagnostics", {}),
    ) from None


def geocode(text):
    routing, _ = providers()
    try:
        candidates = routing.geocode(text)
    except ProviderError as error:
        provider_failure(error)
    return [
        {
            "name": c.label,
            "latitude": number(c.position.latitude),
            "longitude": number(c.position.longitude),
            "timezone": c.timezone_name,
            "entry_points": [coordinate(p) for p in c.entry_points],
        }
        for c in candidates
    ]


class LiveBundle:
    version = LIVE_VERSION

    def __init__(self, inputs, routing, weather):
        self.inputs = inputs
        query = RoutingQuery(
            GeoPoint(inputs["origin"]["latitude"], inputs["origin"]["longitude"]),
            GeoPoint(inputs["destination"]["latitude"], inputs["destination"]["longitude"]),
            inputs["departure_at"],
            truck_restrictions=inputs.get("truck_profile"),
        )
        result = routing.route_candidates(query)
        usable = [
            r
            for r in result.routes
            if r.duplicate_of is None and r.geometry_valid and r.timing_valid
        ]
        if not usable:
            error = ProviderError("NO_TIMED_UNIQUE_ROUTES")
            error.diagnostics = {
                "candidate_quality_flags": [list(r.quality_flags) for r in result.routes],
                "rejections": [r.reason for r in result.rejected],
            }
            raise error
        self.warnings = [
            "PERSONAL NONCOMMERCIAL ASSESSMENT ONLY — not an operational safety or navigation service.",
            "Open-Meteo / DWD ICON Global forecasts; CC BY 4.0. Liquid rain = rain + showers, never total precipitation.",
            "Snowfall is Open-Meteo's provider-derived depth with a fixed 7:1 snow/water relationship; approximation approved for this assessment only, not native NBM depth.",
            "Provider hourly service slots are used; underlying native interval/run identity is not exposed. Forecast runs may be stitched; model_run_at remains null.",
            "TomTom truck routing and interpolated cumulative travel times exclude breaks/stops. Cargo load is separate from physical vehicle totals.",
            "Forecast viewer bins are sampled corridor geography, not native grid boundaries; clock scrubbing never changes the saved recommendation.",
        ]
        if result.usable_unique_count != 3:
            self.warnings.append(
                f"THREE_ROUTE_REQUIREMENT_NOT_MET: {result.usable_unique_count} valid distinct truck candidates; no invented alternative."
            )
        if result.rejected:
            self.warnings.extend(
                f"CANDIDATE_{r.candidate_index + 1}_REJECTED_{r.reason}" for r in result.rejected
            )
        self.fixtures, self.geometries = [], {}
        unique = {}
        eta_end = inputs["departure_at"] + timedelta(hours=49)
        for route in usable:
            geometry = prepare_geometry(route.points, route.progress)
            self.geometries[route.candidate_index] = geometry
            self.fixtures.append(
                {
                    "id": route.route_id,
                    "code": chr(65 + route.candidate_index),
                    "label": f"Truck route {chr(65 + route.candidate_index)}",
                    "candidate_index": route.candidate_index,
                    "points": route.points,
                    "anchors": route.progress,
                    "distance_m": route.distance_m,
                    "duration_seconds": route.duration_seconds,
                    "geometry_valid": route.geometry_valid,
                    "timing_valid": route.timing_valid,
                    "routing_valid": route.routing_valid,
                    "route_notices": list(route.quality_flags) + [n.code for n in route.notices],
                }
            )
            if route.duration_seconds > 48 * 3600:
                raise ProviderError("TRIP_DURATION_EXCEEDS_ASSESSMENT_WINDOW")
            for distance in sample_chainages(route.distance_m, inputs["checkpoint_interval_miles"]):
                point = geometry.point_at(distance)
                unique[point_key(point)] = point
        if len(unique) > 160:
            raise ProviderError("CHECKPOINT_ACQUISITION_LIMIT")
        self.points = tuple(unique.values())
        self.records = {key: [] for key in unique}
        # At most 8 finite batches, 20 coordinates each. Never an automatic retry.
        for start in range(0, len(self.points), 20):
            received = weather.measurements(
                WeatherQuery(
                    self.points[start : start + 20],
                    inputs["departure_at"] - timedelta(hours=1),
                    eta_end,
                )
            )
            for measurement in received:
                self.records[point_key(measurement.requested_point)].append(measurement)

    def observe(self, *, route_index, fraction, requested_at, **unused):
        geometry = self.geometries[route_index]
        point = geometry.point_at(geometry.distance_m * fraction)
        # Decimal division round-trip can differ at the final binary coordinate.
        # Use nearest of this route's exact canonical checkpoint coordinates, <1m.
        from atlas.domain import geodesic_distance_m

        source = min(self.points, key=lambda p: geodesic_distance_m(point, p))
        if geodesic_distance_m(point, source) > 1:
            raise ProviderError("CHECKPOINT_SOURCE_ALIGNMENT_INVALID")
        return select_measurements(self.records[point_key(source)], requested_at)

    def frames(self, inputs):
        cells = []
        for index, point in enumerate(self.points):
            x, y = point.longitude, point.latitude
            cells.append(
                {
                    "id": f"forecast-sample-{index}",
                    "coordinate": coordinate(point),
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [x - 0.18, y - 0.16],
                                [x + 0.18, y - 0.16],
                                [x + 0.18, y + 0.16],
                                [x - 0.18, y + 0.16],
                                [x - 0.18, y - 0.16],
                            ]
                        ],
                    },
                }
            )
        values = {}
        for hour in range(49):
            requested = inputs["departure_at"] + timedelta(hours=hour)
            values[str(hour)] = [
                select_measurements(self.records[point_key(p)], requested)[1] for p in self.points
            ]
        return {
            "cells": cells,
            "values": values,
            "departure_at": iso(inputs["departure_at"]),
            "source_policy": SOURCE_POLICY,
        }


def create_live_analysis(inputs):
    require_live()
    departure = inputs["departure_at"]
    now = timezone.now()
    if not now - timedelta(minutes=5) <= departure <= now + timedelta(hours=48):
        raise AtlasError(
            "FORECAST_DEPARTURE_WINDOW",
            "Live assessment departure must be now through the next 48 hours (five-minute form grace).",
        )
    if inputs["origin"] == inputs["destination"]:
        raise AtlasError("TRIP_ENDPOINTS_EQUAL", "Choose distinct endpoints.")
    if not LIVE_LOCK.acquire(blocking=False):
        raise AtlasError(
            "LIVE_ANALYSIS_BUSY",
            "One live analysis is already running. No new provider call was made.",
            status=429,
        )
    snapshot = None
    try:
        with ADMISSION_LOCK, transaction.atomic():
            AnalysisSnapshot.objects.filter(expires_at__lte=now).delete()
            if AnalysisSnapshot.objects.count() >= settings.ATLAS_MAX_LOCAL_SNAPSHOTS:
                raise AtlasError(
                    "ANALYSIS_ADMISSION_LIMIT", "The local snapshot limit is reached.", status=429
                )
            snapshot = AnalysisSnapshot.objects.create(
                expires_at=now + timedelta(hours=1),
                status=AnalysisSnapshot.Status.RUNNING,
                started_at=now,
            )
        routing, weather = providers()
        bundle = LiveBundle(inputs, routing, weather)
        result, frames = build_result(inputs, snapshot, live_bundle=bundle)
        completed = timezone.now()
        result.update(
            {
                "completed_at": iso(completed),
                "lifecycle": [
                    {"status": "queued", "at": iso(snapshot.created_at)},
                    {"status": "running", "at": iso(snapshot.started_at)},
                    {"status": "complete", "at": iso(completed)},
                ],
            }
        )
        snapshot.result, snapshot.frame_data = result, frames
        snapshot.status, snapshot.completed_at = AnalysisSnapshot.Status.COMPLETE, completed
        snapshot.save(update_fields=["result", "frame_data", "status", "completed_at"])
        return snapshot
    except Exception as error:
        if snapshot:
            snapshot.status = AnalysisSnapshot.Status.FAILED
            snapshot.completed_at = timezone.now()
            snapshot.save(update_fields=["status", "completed_at"])
        if isinstance(error, ProviderError):
            provider_failure(error)
        raise
    finally:
        LIVE_LOCK.release()


def live_frame(snapshot, hour, variable, *, data=None):
    data = snapshot.frame_data if data is None else data
    cells = [
        {**cell, "measurement": values[variable]}
        for cell, values in zip(data["cells"], data["values"][str(hour)])
    ]
    known = sum(c["measurement"]["value"] is not None for c in cells)
    status = "complete" if known == len(cells) else "missing" if known == 0 else "partial"
    return {
        "analysis_id": str(snapshot.id),
        "mode": "live",
        "sample_data": False,
        "hour": hour,
        "variable": variable,
        "requested_at": iso(
            datetime.fromisoformat(data["departure_at"].replace("Z", "+00:00"))
            + timedelta(hours=hour)
        ),
        "unit": "mph" if variable == "wind" else "in/hour",
        "classification_basis": "selected_variable",
        "acquisition_status": "ready" if status == "complete" else status,
        "coverage": {
            "status": status,
            "known_cells": known,
            "total_cells": len(cells),
            "reason_codes": [] if status == "complete" else ["PROVIDER_VALUE_MISSING_OR_INVALID"],
        },
        "cells": cells,
        "warnings": [
            "Open-Meteo / DWD ICON Global — CC BY 4.0. Display bins are sampled corridor locations, not native grid boundaries.",
            "Snowfall uses the provider's fixed 7:1 relationship. Assessment-only approximation.",
            "Clock-time values never rescore the immutable ETA recommendation.",
        ],
    }
