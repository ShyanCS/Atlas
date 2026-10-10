"""TomTom v1 routing/geocoding normalization; not connected to analysis endpoints.

No provider geometry is saved, logged or converted into live weather recommendations.
Normalization version and conservative near-duplicate tolerances are explicit.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from atlas.domain import (
    DomainValidationError,
    GeoPoint,
    ProgressAnchor,
    geodesic_distance_m,
    prepare_geometry,
)
from atlas.providers.interfaces import (
    CommittedLocation,
    GeocodeCandidate,
    NormalizedRoute,
    ProviderCapabilities,
    RouteSection,
    RoutingNotice,
)
from atlas.providers.tomtom_http import ProviderError

NORMALIZATION_VERSION = "tomtom-v1-normalization-1"
NEAR_DUPLICATE_SEPARATION_M = Decimal(75)
NEAR_DUPLICATE_LENGTH_M = Decimal(250)
SNAP_REVIEW_DISTANCE_M = Decimal(25)


@dataclass(frozen=True)
class RejectedCandidate:
    candidate_index: int
    reason: str


@dataclass(frozen=True)
class RoutingResult:
    routes: tuple[NormalizedRoute, ...]
    rejected: tuple[RejectedCandidate, ...]
    requested_count: int
    returned_count: int
    original_report_json: str = field(default="{}", repr=False)

    @property
    def usable_unique_count(self):
        return sum(
            r.duplicate_of is None and r.geometry_valid and r.timing_valid and r.routing_valid
            for r in self.routes
        )

    @property
    def three_candidate_requirement_met(self):
        return self.usable_unique_count >= 3


def decimal_value(value, *, positive=False):
    if isinstance(value, bool) or value is None:
        raise ProviderError("MALFORMED_NUMERIC_VALUE")
    try:
        number = Decimal(str(value))
    except Exception:
        raise ProviderError("MALFORMED_NUMERIC_VALUE") from None
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        raise ProviderError("MALFORMED_NUMERIC_VALUE")
    return number


def canonical_json(value):
    def convert(item):
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError("Unsupported JSON value")

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=convert, allow_nan=False
    )


def absolute(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ProviderError("MALFORMED_PROVIDER_TIME") from None


def validate_query(query):
    if not isinstance(query.origin, GeoPoint) or not isinstance(query.destination, GeoPoint):
        raise ProviderError("INVALID_ROUTE_COORDINATES")
    if (
        not isinstance(query.departure_at, datetime)
        or query.departure_at.tzinfo is None
        or query.departure_at.utcoffset() is None
    ):
        raise ProviderError("DEPARTURE_OFFSET_REQUIRED")
    if isinstance(query.alternative_count, bool) or query.alternative_count not in (0, 1, 2):
        raise ProviderError("INVALID_ALTERNATIVE_COUNT")
    if (
        (query.requested_origin is not None and query.requested_origin != query.origin)
        or (
            query.requested_destination is not None
            and query.requested_destination != query.destination
        )
    ) and not query.access_corrections_confirmed:
        raise ProviderError("ACCESS_CORRECTION_NOT_CONFIRMED")
    mapping = {
        "current_weight_kg": "vehicleWeight",
        "height_m": "vehicleHeight",
        "width_m": "vehicleWidth",
        "length_m": "vehicleLength",
        "axle_weight_kg": "vehicleAxleWeight",
        "axle_count": "vehicleNumberOfAxles",
    }
    params = []
    for name, value in (query.truck_restrictions or {}).items():
        if name not in mapping:
            raise ProviderError("INVALID_TRUCK_PROFILE")
        normalized = decimal_value(value)
        if (
            name in ("current_weight_kg", "axle_weight_kg", "axle_count")
            and normalized != normalized.to_integral_value()
        ):
            raise ProviderError("INTEGER_TRUCK_PARAMETER_REQUIRED")
        params.append((mapping[name], str(normalized)))
    return params


def normalize_one(raw, index, query, top_notices):
    if not isinstance(raw, dict):
        raise ProviderError("MALFORMED_ROUTE")
    summary = raw.get("summary")
    if not isinstance(summary, dict):
        raise ProviderError("MISSING_ROUTE_SUMMARY")
    distance = decimal_value(summary.get("lengthInMeters"), positive=True)
    duration = decimal_value(summary.get("travelTimeInSeconds"), positive=True)
    legs = raw.get("legs")
    if not isinstance(legs, list) or not legs:
        raise ProviderError("MISSING_ROUTE_LEGS")
    try:
        # Preserve provider indexing, including a repeated leg-boundary coordinate.
        points = tuple(
            GeoPoint(p["latitude"], p["longitude"]) for leg in legs for p in leg["points"]
        )
    except (KeyError, TypeError, DomainValidationError):
        raise ProviderError("INVALID_ROUTE_GEOMETRY") from None
    if not 2 <= len(points) <= 100000:
        raise ProviderError("INVALID_ROUTE_GEOMETRY")
    if not any(a != b for a, b in zip(points, points[1:])):
        raise ProviderError("INVALID_ROUTE_GEOMETRY")
    flags = []
    progress = []
    timing_valid = True
    try:
        if not isinstance(raw.get("progress"), list):
            raise ProviderError("PROGRESS_UNAVAILABLE")
        for item in raw["progress"]:
            point_index = item["pointIndex"]
            if not isinstance(point_index, int) or isinstance(point_index, bool):
                raise ProviderError("INVALID_PROGRESS")
            progress.append(
                ProgressAnchor(
                    point_index,
                    decimal_value(item["distanceInMeters"]),
                    decimal_value(item["travelTimeInSeconds"]),
                )
            )
        prepared = prepare_geometry(points, progress)
        if prepared.distance_m != distance or progress[-1].elapsed_seconds != duration:
            raise ProviderError("PROGRESS_SUMMARY_MISMATCH")
    except (KeyError, TypeError, DomainValidationError, ProviderError):
        flags.append("INVALID_OR_MISSING_PROGRESS")
        timing_valid = False
    requested_departure = query.departure_at.astimezone(timezone.utc)
    try:
        departure = absolute(summary.get("departureTime"))
        arrival = absolute(summary.get("arrivalTime"))
    except ProviderError:
        departure, arrival = None, None
    if (
        departure is None
        or arrival is None
        or departure != requested_departure
        or abs(Decimal(str((arrival - departure).total_seconds())) - duration) > Decimal(1)
    ):
        flags.append("SUMMARY_TIME_MISMATCH")
        timing_valid = False
    raw_sections = raw.get("sections")
    sections = []
    routing_valid = True
    if not isinstance(raw_sections, list):
        flags.append("TRAVEL_MODE_COVERAGE_UNAVAILABLE")
        raw_sections = []
        routing_valid = False
    for section in raw_sections:
        try:
            a, b = section["startPointIndex"], section["endPointIndex"]
            if (
                not isinstance(a, int)
                or not isinstance(b, int)
                or isinstance(a, bool)
                or isinstance(b, bool)
                or not 0 <= a < b < len(points)
            ):
                raise ValueError
            kind = section["sectionType"]
            mode = section.get("travelMode")
            sections.append(RouteSection(a, b, kind, mode))
            if kind in ("PEDESTRIAN", "CAR_TRAIN") or (kind == "TRAVEL_MODE" and mode != "truck"):
                flags.append("INCOMPATIBLE_TRAVEL_SECTION")
                routing_valid = False
            if (
                section.get("isPassable") is False
                or section.get("blocked") is True
                or section.get("violated") is True
            ):
                flags.append("HARD_ROUTING_RESTRICTION")
                routing_valid = False
        except (KeyError, TypeError, ValueError):
            flags.append("INVALID_ROUTE_SECTION")
            routing_valid = False
    covered = 0
    for section in sorted(
        (s for s in sections if s.section_type == "TRAVEL_MODE"), key=lambda s: s.start_index
    ):
        if section.start_index > covered:
            break
        covered = max(covered, section.end_index)
    if covered != len(points) - 1:
        flags.append("TRAVEL_MODE_COVERAGE_UNAVAILABLE")
        routing_valid = False
    notices = [*top_notices]
    for owner in (raw, *legs):
        for key in ("notices", "warnings"):
            value = owner.get(key, [])
            if not isinstance(value, list):
                flags.append("UNREVIEWED_NOTICE_FORMAT")
                routing_valid = False
            else:
                notices.extend(value)
    hard = {
        "ROAD_CLOSED",
        "VEHICLE_RESTRICTION_VIOLATION",
        "TRUCK_RESTRICTION_VIOLATION",
        "ROUTE_NOT_DRIVABLE",
    }
    normalized_notices = []
    for notice in notices:
        if not isinstance(notice, dict):
            flags.append("UNREVIEWED_PROVIDER_NOTICE")
            routing_valid = False
            continue
        if (
            str(notice.get("severity", "")).lower() in ("critical", "error", "fatal")
            or notice.get("code") in hard
            or notice.get("violated") is True
        ):
            flags.append("HARD_ROUTING_RESTRICTION")
            routing_valid = False
        elif str(notice.get("severity", "")).lower() not in ("info", "information"):
            flags.append("UNREVIEWED_PROVIDER_NOTICE")
            routing_valid = False
        normalized_notices.append(
            RoutingNotice(
                str(notice.get("code", "UNCLASSIFIED_NOTICE")),
                "critical"
                if notice.get("code") in hard
                or str(notice.get("severity", "")).lower() in ("critical", "error", "fatal")
                or notice.get("violated") is True
                else "info",
                str(notice.get("message", "")),
            )
        )
    if not query.truck_restrictions:
        flags.append("PHYSICAL_VEHICLE_PROFILE_UNSPECIFIED")
    for field_name in (
        "current_weight_kg",
        "height_m",
        "width_m",
        "length_m",
        "axle_weight_kg",
        "axle_count",
    ):
        if not (query.truck_restrictions or {}).get(field_name):
            flags.append("UNSPECIFIED_" + field_name.upper())
    if (
        max(
            geodesic_distance_m(query.origin, points[0]),
            geodesic_distance_m(query.destination, points[-1]),
        )
        > SNAP_REVIEW_DISTANCE_M
    ):
        flags.append("UNCONFIRMED_PROVIDER_SNAP")
        routing_valid = False
    return NormalizedRoute(
        route_id=f"tomtom-candidate-{index}",
        label=f"Provider candidate {index + 1}",
        points=points,
        progress=tuple(progress),
        notices=tuple(normalized_notices),
        distance_m=distance,
        duration_seconds=duration,
        quality_flags=tuple(dict.fromkeys(flags)),
        candidate_index=index,
        departure_at=departure,
        arrival_at=arrival,
        geometry_valid=True,
        timing_valid=timing_valid,
        routing_valid=routing_valid,
        original_notices_json=canonical_json(notices),
        original_sections_json=canonical_json(raw_sections),
        sections=tuple(sections),
        requested_origin=query.requested_origin or query.origin,
        requested_destination=query.requested_destination or query.destination,
        routing_origin=query.origin,
        routing_destination=query.destination,
        resolved_origin=points[0],
        resolved_destination=points[-1],
        origin_snap_m=geodesic_distance_m(query.origin, points[0]),
        destination_snap_m=geodesic_distance_m(query.destination, points[-1]),
    )


def fingerprint(route):
    # Normalized precision suppresses sub-metre coordinate noise; not an edge-ID proof.
    values = [(round(p.latitude, 6), round(p.longitude, 6)) for p in route.points]
    collapsed = [p for i, p in enumerate(values) if i == 0 or p != values[i - 1]]
    return hashlib.sha256(canonical_json(collapsed).encode()).digest()


def near_duplicate(left, right):
    if abs(left.distance_m - right.distance_m) > NEAR_DUPLICATE_LENGTH_M:
        return False
    if not left.timing_valid or not right.timing_valid:
        return False
    a, b = (
        prepare_geometry(left.points, left.progress),
        prepare_geometry(right.points, right.progress),
    )
    for step in range(65):
        fraction = Decimal(step) / 64
        if (
            geodesic_distance_m(
                a.point_at(a.distance_m * fraction), b.point_at(b.distance_m * fraction)
            )
            > NEAR_DUPLICATE_SEPARATION_M
        ):
            return False
    return True


def normalize_routing(payload, query):
    validate_query(query)
    if not isinstance(payload, dict) or not isinstance(payload.get("routes"), list):
        raise ProviderError("MALFORMED_ROUTING_RESPONSE")
    if not 1 <= len(payload["routes"]) <= 3:
        raise ProviderError("UNSUITABLE_ROUTE_COUNT")
    top = []
    for key in ("notices", "warnings"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            raise ProviderError("MALFORMED_TOP_LEVEL_NOTICES")
        top.extend(value)
    routes, rejected = [], []
    for index, raw in enumerate(payload["routes"]):
        try:
            route = normalize_one(raw, index, query, top)
            duplicate = next(
                (
                    r
                    for r in routes
                    if fingerprint(r) == fingerprint(route) or near_duplicate(r, route)
                ),
                None,
            )
            if duplicate is not None:
                route = replace(
                    route,
                    duplicate_of=duplicate.candidate_index,
                    quality_flags=route.quality_flags + ("DUPLICATE_OR_NEAR_DUPLICATE",),
                )
            routes.append(route)
        except (ProviderError, KeyError, TypeError, ValueError, OverflowError) as error:
            rejected.append(
                RejectedCandidate(
                    index, error.code if isinstance(error, ProviderError) else "MALFORMED_ROUTE"
                )
            )
    return RoutingResult(
        tuple(routes),
        tuple(rejected),
        query.alternative_count + 1,
        len(payload["routes"]),
        canonical_json(payload.get("report", {})),
    )


def normalize_geocoding(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ProviderError("MALFORMED_GEOCODING_RESPONSE")
    candidates = []
    for item in payload["results"]:
        try:
            point = GeoPoint(item["position"]["lat"], item["position"]["lon"])
            label = item["address"]["freeformAddress"]
            if not isinstance(label, str) or not label:
                raise ValueError
            entry_points = tuple(
                GeoPoint(p["position"]["lat"], p["position"]["lon"])
                for p in item.get("entryPoints", item.get("entrypoints", []))
            )
            zone_info = item.get("timeZone") or {}
            if not isinstance(zone_info, dict):
                raise ValueError
            zone = zone_info.get("ianaId")
            if zone:
                ZoneInfo(zone)
            candidates.append(GeocodeCandidate(str(item["id"]), label, point, entry_points, zone))
        except (KeyError, TypeError, ValueError, DomainValidationError, ZoneInfoNotFoundError):
            raise ProviderError("MALFORMED_GEOCODING_CANDIDATE") from None
    return tuple(candidates)


def commit_location(
    candidate,
    *,
    requested_coordinate,
    timezone_name,
    access_coordinate=None,
    confirm_correction=False,
    access_basis="selected_geocode_position",
):
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise ProviderError("EXPLICIT_TIMEZONE_REQUIRED") from None
    if candidate.timezone_name and candidate.timezone_name != timezone_name:
        raise ProviderError("TIMEZONE_CONFIRMATION_MISMATCH")
    if not isinstance(requested_coordinate, GeoPoint):
        raise ProviderError("INVALID_COMMITTED_COORDINATE")
    access = access_coordinate or candidate.position
    if not isinstance(access, GeoPoint):
        raise ProviderError("INVALID_ACCESS_COORDINATE")
    changed = access != requested_coordinate
    if changed and confirm_correction is not True:
        raise ProviderError("ACCESS_CORRECTION_NOT_CONFIRMED")
    return CommittedLocation(
        candidate.label,
        requested_coordinate,
        access,
        timezone_name,
        "provider" if candidate.timezone_name else "explicit_caller",
        confirm_correction,
        geodesic_distance_m(requested_coordinate, access),
        access_basis,
    )


class TomTomAdapter:
    capabilities = ProviderCapabilities("tomtom-maps-routing-v1", True, True, True)

    def __init__(self, transport):
        self.transport = transport

    def route_candidates(self, query):
        profile = validate_query(query)
        points = f"{query.origin.latitude},{query.origin.longitude}:{query.destination.latitude},{query.destination.longitude}"
        parameters = [
            ("travelMode", "truck"),
            ("vehicleCommercial", "true"),
            ("routeRepresentation", "polyline"),
            ("extendedRouteRepresentation", "distance"),
            ("extendedRouteRepresentation", "travelTime"),
            ("sectionType", "travelMode"),
            ("sectionType", "pedestrian"),
            ("traffic", "true"),
            ("maxAlternatives", str(query.alternative_count)),
            ("report", "effectiveSettings"),
            (
                "departAt",
                query.departure_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
            *profile,
        ]
        payload = self.transport.get_json(
            "routing", f"/routing/1/calculateRoute/{points}/json", parameters
        )
        return normalize_routing(payload, query)

    def routes(self, query):
        return self.route_candidates(query).routes

    def geocode(self, text):
        if (
            not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 200
            or any(ord(c) < 32 for c in text)
        ):
            raise ProviderError("INVALID_GEOCODING_QUERY")
        payload = self.transport.get_json(
            "geocoding",
            f"/search/2/geocode/{quote(text.strip(), safe='')}.json",
            [("countrySet", "US"), ("limit", "3")],
        )
        return normalize_geocoding(payload)
