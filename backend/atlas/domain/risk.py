"""The disclosed assessment policy. No network calls or UI scoring."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from ._validation import DomainValidationError, optional_decimal, require_decimal

POLICY_VERSION = "atlas-assessment-policy-v1.0.0"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"
    NO_TRAVEL = "no_travel"
    UNKNOWN = "unknown"


ORDINALS = MappingProxyType(
    {
        RiskLevel.LOW: 0,
        RiskLevel.MODERATE: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.SEVERE: 3,
        RiskLevel.NO_TRAVEL: 4,
    }
)


@dataclass(frozen=True)
class WeatherObservation:
    # Adapters must pass None for unsuitable quantity/time/source coverage.
    wind_mph: Decimal | None = None
    rain_in_per_hour: Decimal | None = None
    snow_in_per_hour: Decimal | None = None


@dataclass(frozen=True)
class ConditionResult:
    condition: str
    value: Decimal | None
    level: RiskLevel
    rule_id: str | None


@dataclass(frozen=True)
class RiskResult:
    level: RiskLevel
    complete: bool
    governing_conditions: tuple[str, ...]
    known_lower_bound: RiskLevel | None
    condition_results: tuple[ConditionResult, ...]
    missing_conditions: tuple[str, ...]
    rule_ids: tuple[str, ...]


def classify_wind(wind_mph, cargo_load_lb) -> RiskLevel:
    cargo = require_decimal(cargo_load_lb, "cargo_load_lb")
    wind = optional_decimal(wind_mph)
    if wind is None:
        return RiskLevel.UNKNOWN
    if wind >= 55 or (wind >= 45 and cargo > 30000):
        return RiskLevel.NO_TRAVEL
    if wind >= 45 or (wind >= 35 and cargo > 40000):
        return RiskLevel.SEVERE
    if wind >= 35:
        return RiskLevel.HIGH
    if wind >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(rain_in_per_hour) -> RiskLevel:
    rain = optional_decimal(rain_in_per_hour)
    if rain is None:
        return RiskLevel.UNKNOWN
    if rain > Decimal("1.00"):
        return RiskLevel.NO_TRAVEL
    if rain >= Decimal("0.50"):
        return RiskLevel.SEVERE
    if rain >= Decimal("0.25"):
        return RiskLevel.HIGH
    if rain >= Decimal("0.10"):
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(snow_in_per_hour) -> RiskLevel:
    snow = optional_decimal(snow_in_per_hour)
    if snow is None:
        return RiskLevel.UNKNOWN
    if snow > Decimal("3.0"):
        return RiskLevel.NO_TRAVEL
    if snow >= Decimal("2.0"):
        return RiskLevel.SEVERE
    if snow >= Decimal("1.0"):
        return RiskLevel.HIGH
    if snow >= Decimal("0.5"):
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def evaluate_checkpoint(weather: WeatherObservation, cargo_load_lb) -> RiskResult:
    cargo = require_decimal(cargo_load_lb, "cargo_load_lb")
    results = []
    for name, raw, classifier in (
        ("wind", weather.wind_mph, lambda value: classify_wind(value, cargo)),
        ("rain", weather.rain_in_per_hour, classify_rain),
        ("snow", weather.snow_in_per_hour, classify_snow),
    ):
        value = optional_decimal(raw)
        level = classifier(value)
        rule = None if level is RiskLevel.UNKNOWN else f"{name}.{level.value}"
        if name == "wind" and value is not None:
            if Decimal(45) <= value < 55 and cargo > 30000:
                rule = "wind.cargo_gt_30000.no_travel"
            elif Decimal(35) <= value < 45 and cargo > 40000:
                rule = "wind.cargo_gt_40000.severe"
        results.append(ConditionResult(name, value, level, rule))
    known = [item for item in results if item.level is not RiskLevel.UNKNOWN]
    worst = max((item.level for item in known), key=ORDINALS.__getitem__, default=None)
    missing = tuple(item.condition for item in results if item.level is RiskLevel.UNKNOWN)
    governing = tuple(item for item in known if item.level == worst)
    overall = worst if not missing or worst is RiskLevel.NO_TRAVEL else RiskLevel.UNKNOWN
    return RiskResult(
        overall or RiskLevel.UNKNOWN,
        not missing,
        tuple(item.condition for item in governing),
        worst,
        tuple(results),
        missing,
        tuple(item.rule_id for item in governing if item.rule_id),
    )


_RULE_CRITERIA = MappingProxyType(
    {
        "wind.low": "wind < 25 mph",
        "wind.moderate": "25 <= wind < 35 mph",
        "wind.high": "35 <= wind < 45 mph",
        "wind.severe": "45 <= wind < 55 mph",
        "wind.no_travel": "wind >= 55 mph, for any cargo load",
        "rain.low": "rain < 0.10 in/hour",
        "rain.moderate": "0.10 <= rain < 0.25 in/hour",
        "rain.high": "0.25 <= rain < 0.50 in/hour",
        "rain.severe": "0.50 <= rain <= 1.00 in/hour",
        "rain.no_travel": "rain > 1.00 in/hour",
        "snow.low": "new snowfall < 0.5 in/hour",
        "snow.moderate": "0.5 <= new snowfall < 1.0 in/hour",
        "snow.high": "1.0 <= new snowfall < 2.0 in/hour",
        "snow.severe": "2.0 <= new snowfall <= 3.0 in/hour",
        "snow.no_travel": "new snowfall > 3.0 in/hour",
        "wind.cargo_gt_30000.no_travel": "45 <= wind < 55 mph and cargo > 30,000 lb (strict)",
        "wind.cargo_gt_40000.severe": "35 <= wind < 45 mph and cargo > 40,000 lb (strict)",
    }
)


def explain_checkpoint(
    weather: WeatherObservation, cargo_load_lb, risk: RiskResult | None = None
) -> tuple[str, ...]:
    """Explain canonical decisions, including missing data and strict cargo edges."""
    cargo = require_decimal(cargo_load_lb, "cargo_load_lb")
    canonical = evaluate_checkpoint(weather, cargo)
    if risk is not None and risk != canonical:
        raise DomainValidationError("Explanation risk does not match the canonical inputs")
    risk = canonical

    def label(level):
        return level.value.replace("_", " ").title()

    names = {"wind": "Wind", "rain": "Liquid rain", "snow": "New snowfall depth"}
    lines = []
    for condition in risk.condition_results:
        if condition.value is None:
            lines.append(
                f"{names[condition.condition]} is unavailable; missing data is not treated as Low."
            )
            continue
        unit = "mph" if condition.condition == "wind" else "in/hour"
        cargo_text = f"; cargo {format(cargo, ',f')} lb" if condition.condition == "wind" else ""
        lines.append(
            f"{names[condition.condition]} {format(condition.value, 'f')} {unit}{cargo_text}: "
            f"{_RULE_CRITERIA[condition.rule_id]} => {label(condition.level)}."
        )
        if condition.condition == "wind" and condition.rule_id == "wind.severe" and cargo <= 30000:
            lines.append(
                "The strict cargo > 30,000 lb No Travel override is not activated at or below 30,000 lb."
            )
        elif condition.condition == "wind" and condition.rule_id == "wind.high" and cargo <= 40000:
            lines.append(
                "The strict cargo > 40,000 lb Severe override is not activated at or below 40,000 lb."
            )
    governing = ", ".join(risk.governing_conditions)
    missing = ", ".join(risk.missing_conditions)
    if not risk.complete and risk.level is RiskLevel.NO_TRAVEL:
        lines.append(
            f"Overall No Travel: known {governing} proves the blocker despite missing {missing}; coverage remains incomplete."
        )
    elif not risk.complete:
        lower = (
            f" Known lower bound: {label(risk.known_lower_bound)} from {governing}."
            if risk.known_lower_bound
            else ""
        )
        lines.append(f"Overall Unknown: required {missing} is unavailable.{lower}")
    else:
        lines.append(
            f"Overall {label(risk.level)}: the maximum condition severity after cargo overrides; governing {governing}."
        )
    return tuple(lines)
