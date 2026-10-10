"""Typed acquisition ports. TomTom is locally diagnostic; live analysis is unavailable.

Rain/snow measurements are depth amounts over explicit source intervals.
Only the domain's accepted one-hour slots can become in/hour risk inputs.
Fixture-only route indexes/scenarios are deliberately separate from these ports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Mapping, Protocol, TypedDict

from atlas.domain import GeoPoint, ProgressAnchor

WeatherVariable = Literal["wind", "rain", "snow"]
SampleScenario = Literal["complete", "partial", "no-travel"]


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    is_live: bool
    supports_departure_time: bool
    supports_alternatives: bool


class TruckRestrictions(TypedDict, total=False):
    """Optional measured vehicle totals/dimensions; never cargo-load substitution."""

    current_weight_kg: Decimal
    height_m: Decimal
    width_m: Decimal
    length_m: Decimal
    axle_weight_kg: Decimal
    axle_count: int


@dataclass(frozen=True)
class RoutingQuery:
    origin: GeoPoint
    destination: GeoPoint
    departure_at: datetime  # Validated aware UTC by the application boundary.
    truck_restrictions: TruckRestrictions | None = None
    alternative_count: int = 2  # Requested maximum, not an availability guarantee.
    requested_origin: GeoPoint | None = None
    requested_destination: GeoPoint | None = None
    access_corrections_confirmed: bool = False


@dataclass(frozen=True)
class RoutingNotice:
    code: str
    severity: Literal["info", "critical"]
    message: str


@dataclass(frozen=True)
class NormalizedRoute:
    route_id: str
    label: str
    points: tuple[GeoPoint, ...] = field(repr=False)
    progress: tuple[ProgressAnchor, ...] = field(repr=False)
    distance_m: Decimal
    duration_seconds: Decimal
    notices: tuple[RoutingNotice, ...] = ()
    quality_flags: tuple[str, ...] = ()
    candidate_index: int = 0
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    geometry_valid: bool = False
    timing_valid: bool = False
    routing_valid: bool = False
    original_notices_json: str = field(default="[]", repr=False)
    original_sections_json: str = field(default="[]", repr=False)
    sections: tuple["RouteSection", ...] = ()
    requested_origin: GeoPoint | None = field(default=None, repr=False)
    requested_destination: GeoPoint | None = field(default=None, repr=False)
    routing_origin: GeoPoint | None = field(default=None, repr=False)
    routing_destination: GeoPoint | None = field(default=None, repr=False)
    resolved_origin: GeoPoint | None = field(default=None, repr=False)
    resolved_destination: GeoPoint | None = field(default=None, repr=False)
    origin_snap_m: Decimal | None = None
    destination_snap_m: Decimal | None = None
    duplicate_of: int | None = None


@dataclass(frozen=True)
class RouteSection:
    start_index: int
    end_index: int
    section_type: str
    travel_mode: str | None


@dataclass(frozen=True)
class GeocodeCandidate:
    provider_id: str
    label: str
    position: GeoPoint = field(repr=False)
    entry_points: tuple[GeoPoint, ...] = field(default=(), repr=False)
    timezone_name: str | None = None


@dataclass(frozen=True)
class CommittedLocation:
    label: str
    requested_coordinate: GeoPoint = field(repr=False)
    routing_access_coordinate: GeoPoint = field(repr=False)
    timezone_name: str
    timezone_basis: Literal["provider", "explicit_caller"]
    access_correction_confirmed: bool
    displacement_m: Decimal
    access_basis: str
    # Confirmation describes the caller's selected point, not verified truck/dock legality.


class MeasurementProvenance(TypedDict):
    provider_id: str
    model_id: str | None
    model_run_at: datetime | None
    retrieved_at: datetime
    source_point: GeoPoint | None
    valid_at: datetime | None
    interval_start: datetime | None
    interval_end: datetime | None
    native_interval_seconds: int | None
    native: bool
    missing_reason: str | None
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class WeatherQuery:
    points: tuple[GeoPoint, ...]
    start_at: datetime  # Validated aware UTC window, not a scenario-relative clock.
    end_at: datetime


@dataclass(frozen=True)
class WeatherMeasurement:
    requested_point: GeoPoint
    variable: WeatherVariable
    value: Decimal | None
    unit: Literal["mph", "in"]
    provenance: MeasurementProvenance


@dataclass(frozen=True)
class WeatherCell:
    cell_id: str
    center: GeoPoint
    boundary: tuple[GeoPoint, ...] | None
    measurements: tuple[WeatherMeasurement, ...]


class RoutingProvider(Protocol):
    """Normalized routing boundary; diagnostic TomTom is not a weather analysis."""

    capabilities: ProviderCapabilities

    def routes(self, query: RoutingQuery) -> tuple[NormalizedRoute, ...]: ...


class WeatherProvider(Protocol):
    """External point/time-series boundary; matching/risk stays in the domain."""

    def measurements(self, query: WeatherQuery) -> tuple[WeatherMeasurement, ...]: ...


class WeatherCellProvider(Protocol):
    """Optional native-cell capability; a point API is not presumed to have it."""

    def cells(self, query: WeatherQuery) -> tuple[WeatherCell, ...]: ...


class SampleRouteValues(TypedDict):
    id: str
    code: str
    label: str
    candidate_index: int
    points: tuple[GeoPoint, ...]
    anchors: tuple[ProgressAnchor, ...]
    distance_m: Decimal
    duration_seconds: Decimal


class SampleWeatherValues(TypedDict):
    wind: Decimal | None
    rain: Decimal | None
    snow: Decimal | None


class SampleRoutingFixture(Protocol):
    def candidates(self, inputs: Mapping[str, object]) -> tuple[SampleRouteValues, ...]: ...


class SampleWeatherFixture(Protocol):
    def checkpoint_observation(
        self,
        *,
        route_index: int,
        fraction: Decimal,
        elapsed_hours: Decimal,
        scenario: SampleScenario,
    ) -> SampleWeatherValues: ...


class LiveProviderUnavailable(RuntimeError):
    """Typed boundary: this foundation deliberately has no live provider."""
