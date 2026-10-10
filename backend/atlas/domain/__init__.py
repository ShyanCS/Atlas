"""Pure Spotter Atlas safety domain; all public values are provider independent."""

from ._validation import DomainValidationError
from .geometry import (
    GeoPoint,
    PlacedCheckpoint,
    ProgressAnchor,
    RouteGeometry,
    geodesic_distance_m,
    place_checkpoint,
    prepare_geometry,
    sample_chainages,
    slice_geometry,
)
from .risk import (
    POLICY_VERSION,
    ConditionResult,
    RiskLevel,
    RiskResult,
    WeatherObservation,
    classify_rain,
    classify_snow,
    classify_wind,
    evaluate_checkpoint,
    explain_checkpoint,
)
from .routes import (
    METERS_PER_MILE,
    Exposure,
    Recommendation,
    RiskCheckpoint,
    RiskSpan,
    RouteCandidate,
    RouteEvaluation,
    evaluate_route,
    integrate_exposure,
    meters_to_miles,
    miles_to_meters,
    rank_routes,
)
from .temporal import (
    AccumulationForecast,
    AmbiguousLocalTimeError,
    InstantForecast,
    NonexistentLocalTimeError,
    WindMatch,
    match_hourly_accumulation,
    match_wind,
    resolve_local_departure,
)

__all__ = [name for name in globals() if not name.startswith("_")]
