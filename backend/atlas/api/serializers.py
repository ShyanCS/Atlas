from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from atlas.api.errors import AtlasError
from atlas.domain import (
    AmbiguousLocalTimeError,
    DomainValidationError,
    NonexistentLocalTimeError,
    resolve_local_departure,
)

SAMPLE_ORIGIN = {"name": "Chicago, IL", "latitude": "41.878100", "longitude": "-87.629800"}
SAMPLE_DESTINATION = {"name": "Atlanta, GA", "latitude": "33.749000", "longitude": "-84.388000"}
RISK_LEVELS = ["low", "moderate", "high", "severe", "no_travel", "unknown"]
# Sample construction reserves its model-run lookback and all clock source slots.
# These are datetime representation limits, not live forecast availability limits.
SAMPLE_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc) + timedelta(hours=6)
SAMPLE_UTC_MAX = datetime.max.replace(tzinfo=timezone.utc) - timedelta(hours=50)


def unsupported_departure():
    return AtlasError(
        "DEPARTURE_TIME_UNSUPPORTED",
        "Departure cannot represent the required sample calendar window or local time.",
        details={
            "departure_at": [
                "The UTC sample window must represent departure minus 6 hours through plus 50 hours; "
                "the selected IANA local time must also be representable."
            ]
        },
    )


def validate_sample_departure_window(departure, timezone_name):
    if not SAMPLE_UTC_MIN <= departure <= SAMPLE_UTC_MAX:
        raise unsupported_departure()
    try:
        local = departure.astimezone(ZoneInfo(timezone_name))
        # Validate the same local round trip used when normalizing response inputs.
        resolve_local_departure(local.replace(tzinfo=None), timezone_name, local.fold)
    except OverflowError:
        raise unsupported_departure() from None


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            extra = set(data) - set(self.fields)
            if extra:
                raise serializers.ValidationError({key: "Unknown field." for key in sorted(extra)})
        return super().to_internal_value(data)


class LocationSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal("-90"), max_value=Decimal("90")
    )
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=Decimal("-180"), max_value=Decimal("180")
    )


class TruckProfileSerializer(StrictSerializer):
    current_weight_kg = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    height_m = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.1"),
        max_value=Decimal("10"),
        required=False,
    )
    width_m = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.1"),
        max_value=Decimal("10"),
        required=False,
    )
    length_m = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.1"),
        max_value=Decimal("50"),
        required=False,
    )
    axle_weight_kg = serializers.IntegerField(min_value=1, max_value=50000, required=False)
    axle_count = serializers.IntegerField(min_value=1, max_value=20, required=False)


class AnalysisInputSerializer(StrictSerializer):
    mode = serializers.ChoiceField(
        choices=["sample", "live", "actual"],
        default="sample",
        help_text="Live requires explicit server noncommercial assessment configuration; no sample fallback.",
    )
    scenario = serializers.ChoiceField(
        choices=["complete", "partial", "no-travel"], default="complete"
    )
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure_at = serializers.CharField(
        required=False,
        max_length=40,
        help_text=(
            "ISO8601 absolute instant with explicit offset; optional when departure_local is supplied. "
            "Sample UTC arithmetic from departure minus 6 hours through plus 50 hours and IANA "
            "conversion must fit datetime years 1 through 9999. This is not a live forecast horizon."
        ),
    )
    departure_local = serializers.CharField(
        required=False,
        max_length=32,
        help_text="Naive local ISO datetime resolved by the backend in origin_timezone.",
    )
    departure_fold = serializers.ChoiceField(choices=[0, 1], required=False, allow_null=True)
    origin_timezone = serializers.CharField(max_length=64)
    load_weight_lb = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("200000")
    )
    checkpoint_interval_miles = serializers.ChoiceField(choices=[10, 25, 50])
    truck_profile = TruckProfileSerializer(required=False)

    def validate(self, data):
        for field, wanted in (
            (("origin", SAMPLE_ORIGIN), ("destination", SAMPLE_DESTINATION))
            if data["mode"] == "sample"
            else ()
        ):
            location = data[field]
            if location["name"] != wanted["name"] or any(
                location[k] != Decimal(wanted[k]) for k in ("latitude", "longitude")
            ):
                raise AtlasError(
                    "SAMPLE_LOCATION_UNAVAILABLE",
                    "Select the named Chicago-to-Atlanta sample endpoints; geocoding and arbitrary locations are unavailable.",
                    details={field: ["Use the committed endpoint returned by /api/v1/scenarios/."]},
                )
        try:
            ZoneInfo(data["origin_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError(
                {"origin_timezone": "Use a valid IANA time-zone name."}
            )
        absolute = None
        if data.get("departure_at"):
            try:
                absolute = datetime.fromisoformat(data["departure_at"].replace("Z", "+00:00"))
            except ValueError:
                raise serializers.ValidationError(
                    {"departure_at": "Use an ISO8601 timestamp with an explicit UTC offset."}
                )
            if absolute.tzinfo is None or absolute.utcoffset() is None:
                raise serializers.ValidationError(
                    {"departure_at": "An explicit UTC offset is required."}
                )
            try:
                absolute = absolute.astimezone(timezone.utc)
            except OverflowError:
                raise unsupported_departure() from None
        local = None
        if data.get("departure_local"):
            try:
                local = resolve_local_departure(
                    data["departure_local"], data["origin_timezone"], data.get("departure_fold")
                )
            except OverflowError:
                raise unsupported_departure() from None
            except AmbiguousLocalTimeError:
                raise AtlasError(
                    "DEPARTURE_TIME_AMBIGUOUS",
                    "This local time occurs twice. Choose the first or second occurrence.",
                    details={"departure_fold": ["0 = first occurrence; 1 = second occurrence."]},
                )
            except NonexistentLocalTimeError:
                raise AtlasError(
                    "DEPARTURE_TIME_NONEXISTENT",
                    "This local time does not exist because the clock moves forward.",
                    details={"departure_local": ["Choose a different local time."]},
                )
            except DomainValidationError:
                raise serializers.ValidationError(
                    {
                        "departure_local": "Use a valid naive local ISO datetime and optional occurrence 0 or 1."
                    }
                )
        if absolute is None and local is None:
            raise serializers.ValidationError(
                {"departure_at": "Supply departure_at or departure_local with origin_timezone."}
            )
        if absolute is not None and local is not None and absolute != local:
            raise AtlasError(
                "DEPARTURE_TIME_INCONSISTENT",
                "The absolute and local departure values describe different instants.",
            )
        data["departure_at"] = absolute or local
        if data["mode"] != "sample" and data["departure_at"].microsecond:
            raise AtlasError(
                "LIVE_DEPARTURE_PRECISION",
                "Live routing requires departure at whole-second precision; fractional seconds are not silently rounded.",
            )
        validate_sample_departure_window(data["departure_at"], data["origin_timezone"])
        return data


class CoordinateSerializer(serializers.Serializer):
    latitude = serializers.CharField()
    longitude = serializers.CharField()


class LineGeometrySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=2,
    )


class PolygonGeometrySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["Polygon"])
    coordinates = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2)
        )
    )


class ProvenanceSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["synthetic", "forecast"])
    source = serializers.CharField()
    model = serializers.CharField()
    model_run_at = serializers.DateTimeField(allow_null=True)
    valid_at = serializers.DateTimeField(allow_null=True)
    interval_start = serializers.DateTimeField(allow_null=True)
    interval_end = serializers.DateTimeField(allow_null=True)
    native_interval_seconds = serializers.IntegerField(allow_null=True)
    retrieved_at = serializers.DateTimeField()
    quality_flags = serializers.ListField(child=serializers.CharField())
    source_point = CoordinateSerializer(allow_null=True, required=False)
    source_policy = serializers.CharField(required=False)


class MeasurementSerializer(serializers.Serializer):
    value = serializers.CharField(allow_null=True)
    unit = serializers.ChoiceField(choices=["mph", "in/hour"])
    missing_reason = serializers.CharField(allow_null=True)
    provenance = ProvenanceSerializer()


class MeasurementsSerializer(serializers.Serializer):
    wind = MeasurementSerializer()
    rain = MeasurementSerializer()
    snow = MeasurementSerializer()


class CheckpointSerializer(serializers.Serializer):
    id = serializers.CharField()
    route_id = serializers.CharField()
    index = serializers.IntegerField()
    label = serializers.CharField()
    distance_mi = serializers.CharField()
    eta_utc = serializers.DateTimeField()
    coordinate = CoordinateSerializer()
    overall_risk = serializers.ChoiceField(choices=RISK_LEVELS)
    complete = serializers.BooleanField()
    governing_conditions = serializers.ListField(child=serializers.CharField())
    known_lower_bound = serializers.ChoiceField(choices=RISK_LEVELS, allow_null=True)
    rule_ids = serializers.ListField(child=serializers.CharField())
    rule_explanations = serializers.ListField(child=serializers.CharField())
    measurements = MeasurementsSerializer()
    timing_quality = serializers.CharField()
    anchor_gap_mi = serializers.CharField()
    anchor_gap_seconds = serializers.CharField()


class RiskSpanSerializer(serializers.Serializer):
    start_mi = serializers.CharField()
    end_mi = serializers.CharField()
    classification = serializers.ChoiceField(choices=RISK_LEVELS)
    geometry = LineGeometrySerializer()
    checkpoint_ids = serializers.ListField(child=serializers.CharField())
    governing_conditions = serializers.ListField(child=serializers.CharField())


class ExposureSerializer(serializers.Serializer):
    low_mi = serializers.CharField()
    moderate_mi = serializers.CharField()
    high_mi = serializers.CharField()
    severe_mi = serializers.CharField()
    no_travel_mi = serializers.CharField()
    unknown_mi = serializers.CharField()


class RouteSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    label = serializers.CharField()
    geometry = LineGeometrySerializer()
    distance_mi = serializers.CharField()
    duration_seconds = serializers.IntegerField()
    departure_at = serializers.DateTimeField()
    arrival_at = serializers.DateTimeField()
    exposure = ExposureSerializer()
    average_risk = serializers.CharField(allow_null=True)
    verified_fraction = serializers.CharField()
    eligible = serializers.BooleanField()
    eligibility_reasons = serializers.ListField(child=serializers.CharField())
    rank = serializers.IntegerField(allow_null=True)
    checkpoints = CheckpointSerializer(many=True)
    risk_spans = RiskSpanSerializer(many=True)
    route_notices = serializers.ListField(child=serializers.CharField())
    timing_quality = serializers.CharField()
    routing_eligibility_basis = serializers.ChoiceField(
        choices=["authored_sample_assumption", "provider_truck_sections_and_notices"]
    )


class RecommendationSerializer(serializers.Serializer):
    route_id = serializers.CharField(allow_null=True)
    state = serializers.ChoiceField(choices=["recommended", "blocked", "unverified"])
    reason = serializers.CharField()
    ranking_criteria = serializers.ListField(child=serializers.CharField())


class LifecycleEntrySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["queued", "running", "complete"])
    at = serializers.DateTimeField()


class AnalysisInputsSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure_at = serializers.DateTimeField()
    departure_local = serializers.CharField(allow_null=True)
    departure_fold = serializers.IntegerField(allow_null=True)
    origin_timezone = serializers.CharField()
    load_weight_lb = serializers.CharField()
    checkpoint_interval_miles = serializers.IntegerField()
    truck_profile = TruckProfileSerializer(required=False)


class AnalysisSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["complete"])
    mode = serializers.ChoiceField(choices=["sample", "live"])
    sample_data = serializers.BooleanField()
    scenario = serializers.ChoiceField(choices=["complete", "partial", "no-travel"])
    policy_version = serializers.CharField()
    fixture_version = serializers.CharField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    lifecycle = LifecycleEntrySerializer(many=True)
    inputs = AnalysisInputsSerializer()
    routes = RouteSerializer(many=True)
    recommendation = RecommendationSerializer()
    warnings = serializers.ListField(child=serializers.CharField())


class FrameQuerySerializer(StrictSerializer):
    hour = serializers.IntegerField(min_value=0, max_value=48)
    variable = serializers.ChoiceField(choices=["wind", "rain", "snow"])


class FrameCoverageSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["complete", "partial", "missing"])
    known_cells = serializers.IntegerField()
    total_cells = serializers.IntegerField()
    reason_codes = serializers.ListField(child=serializers.CharField())


class FrameCellSerializer(serializers.Serializer):
    id = serializers.CharField()
    geometry = PolygonGeometrySerializer()
    coordinate = CoordinateSerializer()
    measurement = MeasurementSerializer()


class FrameSerializer(serializers.Serializer):
    analysis_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["sample", "live"])
    sample_data = serializers.BooleanField()
    hour = serializers.IntegerField()
    variable = serializers.ChoiceField(choices=["wind", "rain", "snow"])
    requested_at = serializers.DateTimeField()
    unit = serializers.CharField()
    classification_basis = serializers.ChoiceField(choices=["selected_variable"])
    acquisition_status = serializers.ChoiceField(choices=["ready", "partial", "missing"])
    coverage = FrameCoverageSerializer()
    cells = FrameCellSerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())


class ScenarioSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=["complete", "partial", "no-travel"])
    label = serializers.CharField()
    description = serializers.CharField()


class DefaultsSerializer(serializers.Serializer):
    departure_at = serializers.DateTimeField()
    departure_local = serializers.CharField()
    departure_fold = serializers.IntegerField(allow_null=True)
    origin_timezone = serializers.CharField()
    load_weight_lb = serializers.CharField()
    checkpoint_interval_miles = serializers.IntegerField()


class ScenarioLocationsSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()


class ScenariosSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["sample"])
    sample_data = serializers.BooleanField()
    locations = ScenarioLocationsSerializer()
    defaults = DefaultsSerializer()
    scenarios = ScenarioSerializer(many=True)


class HealthSerializer(serializers.Serializer):
    assessment_access_required = serializers.BooleanField()
    status = serializers.ChoiceField(choices=["ok"])
    mode = serializers.ChoiceField(choices=["sample"])
    live_available = serializers.BooleanField()
    policy_version = serializers.CharField()
    version = serializers.CharField()


class GeocodeInputSerializer(StrictSerializer):
    text = serializers.CharField(min_length=1, max_length=200)


class GeocodeCandidateSerializer(serializers.Serializer):
    name = serializers.CharField()
    latitude = serializers.CharField()
    longitude = serializers.CharField()
    timezone = serializers.CharField(allow_null=True)
    entry_points = CoordinateSerializer(many=True)


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorResponseSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()
    request_id = serializers.UUIDField()
