"""Synchronous sample orchestration around the network-free domain engine."""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone as django_timezone

from atlas.api.errors import AtlasError
from atlas.domain import (
    POLICY_VERSION,
    AccumulationForecast,
    AmbiguousLocalTimeError,
    InstantForecast,
    RiskCheckpoint,
    RouteCandidate,
    WeatherObservation,
    evaluate_checkpoint,
    explain_checkpoint,
    match_hourly_accumulation,
    match_wind,
    meters_to_miles,
    prepare_geometry,
    rank_routes,
    resolve_local_departure,
    sample_chainages,
)
from atlas.models import AnalysisSnapshot
from atlas.providers.interfaces import SampleRoutingFixture, SampleWeatherFixture
from atlas.providers.sample import FIXTURE_VERSION, SampleRoutingProvider, SampleWeatherProvider

ROUTING: SampleRoutingFixture = SampleRoutingProvider()
WEATHER: SampleWeatherFixture = SampleWeatherProvider()
RANKING_CRITERIA = ["severe_mi", "high_mi", "average_risk", "duration_seconds"]
ADMISSION_LOCK = Lock()  # Single local process only; not a distributed quota claim.


def number(value, places=6):
    if value is None:
        return None
    return format(Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), "f")


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def coordinate(point):
    return {
        "latitude": number(Decimal(str(point.latitude))),
        "longitude": number(Decimal(str(point.longitude))),
    }


def line_geometry(points):
    return {
        "type": "LineString",
        "coordinates": [[point.longitude, point.latitude] for point in points],
    }


def measurement(
    value, variable, *, valid_at, interval_start, interval_end, model_run_at, retrieved_at
):
    quality = ["SAMPLE_DATA", "AUTHORED_ILLUSTRATION"]
    if variable == "snow":
        quality.append("HYPOTHETICAL_NATIVE_DEPTH")
    return {
        "value": str(value) if value is not None else None,
        "unit": "mph" if variable == "wind" else "in/hour",
        "missing_reason": "ILLUSTRATIVE_SOURCE_WINDOW_UNAVAILABLE" if value is None else None,
        "provenance": {
            "kind": "synthetic",
            "source": "Spotter Atlas authored sample",
            "model": "atlas-sample-v1",
            "model_run_at": iso(model_run_at),
            "valid_at": iso(valid_at),
            "interval_start": iso(interval_start) if interval_start else None,
            "interval_end": iso(interval_end) if interval_end else None,
            "native_interval_seconds": 3600 if variable != "wind" else None,
            "retrieved_at": iso(retrieved_at),
            "quality_flags": quality,
        },
    }


def source_measurements(
    *, route_index, fraction, requested_at, departure_at, scenario, model_run_at, retrieved_at
):
    """Generate explicit illustrative hourly slots, then use the canonical matchers.

    A field's value and provenance always come from the same selected slot.
    A null slot does not become zero or a different forecast hour.
    """
    base = requested_at.replace(minute=0, second=0, microsecond=0)
    times = tuple(base + timedelta(hours=offset) for offset in (-1, 0, 1, 2))
    slot_values = {}
    for valid_at in times:
        delta = valid_at - departure_at
        elapsed = Decimal(delta.days * 86400 + delta.seconds) / Decimal(3600) + Decimal(
            delta.microseconds
        ) / Decimal(3_600_000_000)
        values = WEATHER.checkpoint_observation(
            route_index=route_index, fraction=fraction, elapsed_hours=elapsed, scenario=scenario
        )
        # The illustrative clock changes values at source instants, not at arbitrary ETA minutes.
        values["wind"] += (elapsed % Decimal(7)) * Decimal(".7")
        values["rain"] += (elapsed % Decimal(5)) * Decimal(".015")
        slot_values[valid_at] = values
    wind_slots = tuple(
        InstantForecast(valid_at, slot_values[valid_at]["wind"]) for valid_at in times
    )
    wind = match_wind(requested_at, wind_slots)
    outputs, matched_values = {}, {}
    for variable in ("wind", "rain", "snow"):
        if variable == "wind":
            selected = wind.sample if wind else None
            value = selected.value if selected else None
            # No usable native sample has no asserted source valid instant.
            valid_at = selected.valid_at if selected else requested_at
            interval_start = interval_end = None
        else:
            slots = tuple(
                AccumulationForecast(
                    valid_at - timedelta(hours=1), valid_at, slot_values[valid_at][variable]
                )
                for valid_at in times
            )
            selected = match_hourly_accumulation(requested_at, slots)
            value = selected.value if selected else None
            # Preserve the explicit null interval when the matcher rejects unavailable depth.
            candidate = next(slot for slot in slots if slot.start_at < requested_at <= slot.end_at)
            valid_at = selected.end_at if selected else candidate.end_at
            interval_start = selected.start_at if selected else candidate.start_at
            interval_end = selected.end_at if selected else candidate.end_at
        matched_values[variable] = value
        outputs[variable] = measurement(
            value,
            variable,
            valid_at=valid_at,
            interval_start=interval_start,
            interval_end=interval_end,
            model_run_at=model_run_at,
            retrieved_at=retrieved_at,
        )
    return matched_values, outputs


def build_result(inputs, snapshot, *, live_bundle=None):
    departure = inputs["departure_at"]
    model_run = (departure - timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
    fixtures = live_bundle.fixtures if live_bundle else ROUTING.candidates(inputs)
    candidate_routes, route_outputs, geometries = [], {}, {}
    for fixture in fixtures:
        route_id = fixture["id"]
        geometry = prepare_geometry(fixture["points"], fixture["anchors"])
        geometries[route_id] = geometry
        checkpoints, observations = [], []
        distances = sample_chainages(fixture["distance_m"], inputs["checkpoint_interval_miles"])
        for index, distance in enumerate(distances):
            placed = geometry.place(distance, departure)
            values, measurements = (live_bundle.observe if live_bundle else source_measurements)(
                route_index=fixture["candidate_index"],
                fraction=distance / fixture["distance_m"],
                requested_at=placed.eta_utc,
                departure_at=departure,
                scenario=inputs["scenario"],
                model_run_at=model_run,
                retrieved_at=snapshot.started_at,
            )
            weather = WeatherObservation(values["wind"], values["rain"], values["snow"])
            risk = evaluate_checkpoint(weather, inputs["load_weight_lb"])
            checkpoint_id = f"{route_id}-cp-{index}"
            observations.append(RiskCheckpoint(distance, risk, placed.eta_utc, checkpoint_id))
            checkpoints.append(
                {
                    "id": checkpoint_id,
                    "route_id": route_id,
                    "index": index,
                    "label": "Start"
                    if index == 0
                    else "Finish"
                    if index == len(distances) - 1
                    else f"CP{index}",
                    "distance_mi": str(meters_to_miles(distance)),
                    "eta_utc": iso(placed.eta_utc),
                    "coordinate": coordinate(placed.point),
                    "overall_risk": risk.level.value,
                    "complete": risk.complete,
                    "governing_conditions": list(risk.governing_conditions),
                    "known_lower_bound": risk.known_lower_bound.value
                    if risk.known_lower_bound
                    else None,
                    "rule_ids": list(risk.rule_ids),
                    "rule_explanations": list(
                        explain_checkpoint(weather, inputs["load_weight_lb"], risk)
                    ),
                    "measurements": measurements,
                    "timing_quality": "SYNTHETIC_CUMULATIVE_ANCHORS_INTERPOLATED",
                    "anchor_gap_mi": number(meters_to_miles(placed.anchor_gap_m)),
                    "anchor_gap_seconds": number(placed.anchor_gap_seconds),
                }
            )
        candidate_routes.append(
            RouteCandidate(
                route_id,
                fixture["candidate_index"],
                fixture["distance_m"],
                fixture["duration_seconds"],
                tuple(observations),
                routing_valid=fixture.get("routing_valid", True),
                timing_valid=fixture.get("timing_valid", True),
                geometry_valid=fixture.get("geometry_valid", True),
            )
        )
        route_outputs[route_id] = {
            "id": route_id,
            "code": fixture["code"],
            "label": fixture["label"],
            "geometry": line_geometry(fixture["points"]),
            "distance_mi": str(meters_to_miles(fixture["distance_m"])),
            "duration_seconds": int(fixture["duration_seconds"]),
            "departure_at": iso(departure),
            "arrival_at": iso(checkpoints and observations[-1].eta_utc),
            "checkpoints": checkpoints,
            "route_notices": fixture.get(
                "route_notices",
                [
                    "SAMPLE_GEOMETRY_NOT_ROAD_NAVIGATION",
                    "SYNTHETIC_VEHICLE_RESTRICTIONS_UNVERIFIED",
                ],
            ),
            "timing_quality": "PROVIDER_CUMULATIVE_ANCHORS_INTERPOLATED"
            if live_bundle
            else "SYNTHETIC_CUMULATIVE_ANCHORS_INTERPOLATED",
            "routing_eligibility_basis": "provider_truck_sections_and_notices"
            if live_bundle
            else "authored_sample_assumption",
        }
    recommendation = rank_routes(tuple(candidate_routes))
    eligible_rank = 0
    for evaluation in recommendation.ordered_routes:
        output = route_outputs[evaluation.route.route_id]
        exposure = evaluation.exposure
        if exposure is None:
            raise AtlasError(
                "SAMPLE_FIXTURE_INVALID",
                "The authored route fixture failed validation.",
                status=500,
            )
        if evaluation.eligible:
            eligible_rank += 1
        output.update(
            {
                "exposure": {
                    f"{level.value}_mi": str(meters_to_miles(value))
                    for level, value in exposure.distance_by_level_m.items()
                },
                "average_risk": str(exposure.average_risk)
                if exposure.average_risk is not None
                else None,
                "verified_fraction": str(exposure.complete_fraction),
                "eligible": evaluation.eligible,
                "eligibility_reasons": list(evaluation.disqualification_reasons),
                "rank": eligible_rank if evaluation.eligible else None,
                "risk_spans": [
                    {
                        "start_mi": str(meters_to_miles(span.start_m)),
                        "end_mi": str(meters_to_miles(span.end_m)),
                        "classification": span.level.value,
                        "geometry": line_geometry(
                            geometries[evaluation.route.route_id].slice(span.start_m, span.end_m)
                        ),
                        "checkpoint_ids": [span.checkpoint_id],
                        "governing_conditions": output["checkpoints"][span.checkpoint_index][
                            "governing_conditions"
                        ],
                    }
                    for span in exposure.spans
                ],
            }
        )
    local_departure = departure.astimezone(ZoneInfo(inputs["origin_timezone"]))
    wall_departure = local_departure.replace(tzinfo=None)
    try:
        resolve_local_departure(wall_departure, inputs["origin_timezone"])
        normalized_fold = None
    except AmbiguousLocalTimeError:
        normalized_fold = local_departure.fold
    normalized_inputs = {
        "origin": {k: str(v) for k, v in inputs["origin"].items()},
        "destination": {k: str(v) for k, v in inputs["destination"].items()},
        "departure_at": iso(departure),
        "departure_local": wall_departure.isoformat(),
        "departure_fold": normalized_fold,
        "origin_timezone": inputs["origin_timezone"],
        "load_weight_lb": str(inputs["load_weight_lb"]),
        "checkpoint_interval_miles": inputs["checkpoint_interval_miles"],
    }
    if live_bundle and inputs.get("truck_profile"):
        normalized_inputs["truck_profile"] = {
            key: str(value) for key, value in inputs["truck_profile"].items()
        }
    state = (
        "recommended"
        if recommendation.recommended_route_id
        else "blocked"
        if any("NO_TRAVEL" in route["eligibility_reasons"] for route in route_outputs.values())
        else "unverified"
    )
    result = {
        "id": str(snapshot.id),
        "status": "complete",
        "mode": "live" if live_bundle else "sample",
        "sample_data": not bool(live_bundle),
        "scenario": inputs["scenario"],
        "policy_version": POLICY_VERSION,
        "fixture_version": live_bundle.version if live_bundle else FIXTURE_VERSION,
        "created_at": iso(snapshot.created_at),
        "started_at": iso(snapshot.started_at),
        "expires_at": iso(snapshot.expires_at),
        "inputs": normalized_inputs,
        "routes": list(route_outputs.values()),
        "recommendation": {
            "route_id": recommendation.recommended_route_id,
            "state": state,
            "reason": "First eligible route under the exact assessment priority order."
            if state == "recommended"
            else "No qualified recommendation: at least one required eligibility condition fails on every route.",
            "ranking_criteria": RANKING_CRITERIA,
        },
        "warnings": [
            "SAMPLE DATA — original illustrative geometry and weather; no live providers.",
            "Recommendations demonstrate this policy only; no road legality or travel safety guarantee.",
            "Timing excludes stops, rest and duty rules.",
            "Snow depth semantics are hypothetical hourly fixture data; unavailable after the illustrative 24-hour window.",
        ],
    }
    if live_bundle:
        result["warnings"] = live_bundle.warnings
        for route in result["routes"]:
            for checkpoint in route["checkpoints"]:
                checkpoint["timing_quality"] = route["timing_quality"]
        frame_data = live_bundle.frames(inputs)
    else:
        frame_data = build_frame_data(inputs, geometries["route-a"], model_run, snapshot.started_at)
    return result, frame_data


def build_frame_data(inputs, geometry, model_run, retrieved_at):
    cells = []
    for index in range(32):
        point = geometry.point_at(geometry.distance_m * Decimal(index) / Decimal(31))
        x, y = point.longitude, point.latitude
        polygon = {
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
        }
        cells.append(
            {"id": f"sample-cell-{index}", "geometry": polygon, "coordinate": coordinate(point)}
        )
    values = {}
    for hour in range(49):
        frame_values = []
        for index in range(32):
            _, measurements = source_measurements(
                route_index=0,
                fraction=Decimal(index) / Decimal(31),
                requested_at=inputs["departure_at"] + timedelta(hours=hour),
                departure_at=inputs["departure_at"],
                scenario=inputs["scenario"],
                model_run_at=model_run,
                retrieved_at=retrieved_at,
            )
            # Store both value and its actual illustrative source interval. Shared metadata is compacted.
            frame_values.append(
                {
                    v: {
                        "value": measurements[v]["value"],
                        "valid_at": measurements[v]["provenance"]["valid_at"],
                        "interval_start": measurements[v]["provenance"]["interval_start"],
                        "interval_end": measurements[v]["provenance"]["interval_end"],
                    }
                    for v in ("wind", "rain", "snow")
                }
            )
        values[str(hour)] = frame_values
    return {
        "cells": cells,
        "values": values,
        "model_run_at": iso(model_run),
        "retrieved_at": iso(retrieved_at),
        "departure_at": iso(inputs["departure_at"]),
    }


def create_analysis(inputs, *, public_example_key=None):
    if inputs.get("mode") in {"live", "actual"}:
        if public_example_key is not None:
            raise AtlasError("VALIDATION_ERROR", "Examples cannot acquire provider data.")
        from atlas.services.live import create_live_analysis

        return create_live_analysis(inputs)
    now = django_timezone.now()
    with ADMISSION_LOCK, transaction.atomic():
        AnalysisSnapshot.objects.filter(expires_at__lte=now).delete()
        if public_example_key is None and (
            AnalysisSnapshot.objects.filter(public_example_key__isnull=True).count()
            >= settings.ATLAS_MAX_LOCAL_SNAPSHOTS
        ):
            raise AtlasError(
                "SAMPLE_ADMISSION_LIMIT", "The local sample snapshot limit is reached.", status=429
            )
        snapshot = AnalysisSnapshot.objects.create(
            expires_at=now + timedelta(hours=settings.ATLAS_SNAPSHOT_RETENTION_HOURS),
            public_example_key=public_example_key,
        )
    snapshot.status = AnalysisSnapshot.Status.RUNNING
    snapshot.started_at = django_timezone.now()
    snapshot.save(update_fields=["status", "started_at"])
    try:
        result, frame_data = build_result(inputs, snapshot)
        snapshot.completed_at = django_timezone.now()
        result["completed_at"] = iso(snapshot.completed_at)
        result["lifecycle"] = [
            {"status": "queued", "at": iso(snapshot.created_at)},
            {"status": "running", "at": iso(snapshot.started_at)},
            {"status": "complete", "at": iso(snapshot.completed_at)},
        ]
        snapshot.result, snapshot.frame_data, snapshot.status = (
            result,
            frame_data,
            AnalysisSnapshot.Status.COMPLETE,
        )
        snapshot.save(update_fields=["result", "frame_data", "status", "completed_at"])
        return snapshot
    except Exception:
        snapshot.status = AnalysisSnapshot.Status.FAILED
        snapshot.completed_at = django_timezone.now()
        snapshot.save(update_fields=["status", "completed_at"])
        raise


def get_analysis(analysis_id):
    try:
        snapshot = AnalysisSnapshot.objects.defer("frame_data").get(id=analysis_id)
    except AnalysisSnapshot.DoesNotExist:
        raise AtlasError("ANALYSIS_NOT_FOUND", "This local analysis does not exist.", status=404)
    if snapshot.expires_at <= django_timezone.now():
        raise AtlasError("ANALYSIS_EXPIRED", "This local sample snapshot has expired.", status=410)
    if snapshot.status != AnalysisSnapshot.Status.COMPLETE:
        raise AtlasError(
            "ANALYSIS_NOT_READY", "The synchronous local analysis did not complete.", status=409
        )
    if (
        snapshot.result.get("mode") == "sample"
        and snapshot.result.get("fixture_version") != FIXTURE_VERSION
    ):
        raise AtlasError(
            "ANALYSIS_VERSION_UNAVAILABLE",
            "This preliminary local sample uses an older contract. Create a new sample analysis.",
            status=409,
        )
    return snapshot


def get_frame(snapshot, hour, variable):
    if connection.vendor == "postgresql":
        # Fetch just one hourly JSON slice, not the entire 49-position series.
        names = ("cells", "departure_at", "model_run_at", "retrieved_at", "source_policy")
        fields = [f"frame_data__{name}" for name in names]
        values_key = f"frame_data__values__{hour}"
        selected = AnalysisSnapshot.objects.filter(pk=snapshot.pk).values(*fields, values_key).get()
        stored = {name: selected[f"frame_data__{name}"] for name in names}
        stored["values"] = {str(hour): selected[values_key]}
    else:
        stored = snapshot.frame_data
    if snapshot.result.get("mode") == "live":
        from atlas.services.live import live_frame

        return live_frame(snapshot, hour, variable, data=stored)
    requested = datetime.fromisoformat(stored["departure_at"].replace("Z", "+00:00")) + timedelta(
        hours=hour
    )
    model_run = datetime.fromisoformat(stored["model_run_at"].replace("Z", "+00:00"))
    retrieved = datetime.fromisoformat(stored["retrieved_at"].replace("Z", "+00:00"))

    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None

    cells = [
        {
            **cell,
            "measurement": measurement(
                Decimal(values[variable]["value"])
                if values[variable]["value"] is not None
                else None,
                variable,
                valid_at=parse(values[variable]["valid_at"]),
                interval_start=parse(values[variable]["interval_start"]),
                interval_end=parse(values[variable]["interval_end"]),
                model_run_at=model_run,
                retrieved_at=retrieved,
            ),
        }
        for cell, values in zip(stored["cells"], stored["values"][str(hour)])
    ]
    known = sum(cell["measurement"]["value"] is not None for cell in cells)
    status = "complete" if known == len(cells) else "missing" if known == 0 else "partial"
    return {
        "analysis_id": str(snapshot.id),
        "mode": "sample",
        "sample_data": True,
        "hour": hour,
        "variable": variable,
        "requested_at": iso(requested),
        "unit": "mph" if variable == "wind" else "in/hour",
        "classification_basis": "selected_variable",
        "acquisition_status": "ready" if status == "complete" else status,
        "coverage": {
            "status": status,
            "known_cells": known,
            "total_cells": len(cells),
            "reason_codes": []
            if status == "complete"
            else ["ILLUSTRATIVE_SOURCE_WINDOW_UNAVAILABLE"],
        },
        "cells": cells,
        "warnings": [
            "SAMPLE DATA — illustrative regular cells, not observed/model-native geography.",
            "This clock-time frame never changes the ETA recommendation.",
        ],
    }
