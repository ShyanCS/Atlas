"""Timezone resolution and matching against explicit native forecast slots."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ._validation import DomainValidationError, optional_decimal, utc_datetime


class AmbiguousLocalTimeError(DomainValidationError):
    code = "DEPARTURE_TIME_AMBIGUOUS"


class NonexistentLocalTimeError(DomainValidationError):
    code = "DEPARTURE_TIME_NONEXISTENT"


def resolve_local_departure(local_datetime, timezone_name, fold=None):
    if fold is not None and (isinstance(fold, bool) or fold not in (0, 1)):
        raise DomainValidationError("fold must be omitted, 0 or 1")
    if isinstance(local_datetime, str):
        try:
            local_datetime = datetime.fromisoformat(local_datetime)
        except ValueError:
            raise DomainValidationError("Invalid local departure datetime") from None
    if not isinstance(local_datetime, datetime) or local_datetime.tzinfo is not None:
        raise DomainValidationError("Local departure must be a wall time without an offset")
    if not isinstance(timezone_name, str) or not timezone_name:
        raise DomainValidationError("An IANA timezone is required")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainValidationError("Unknown IANA timezone") from None
    occurrences = {}
    for occurrence in (0, 1):
        candidate = local_datetime.replace(tzinfo=zone, fold=occurrence).astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == local_datetime:
            occurrences[occurrence] = candidate
    if not occurrences:
        raise NonexistentLocalTimeError("Departure falls in a nonexistent DST local time")
    if len(set(occurrences.values())) > 1 and fold is None:
        raise AmbiguousLocalTimeError("Departure occurs twice; explicitly choose fold 0 or 1")
    return occurrences[fold] if fold is not None else occurrences[min(occurrences)]


def timedelta_decimal_seconds(value):
    return Decimal(value.days * 86400 + value.seconds) + Decimal(value.microseconds) / Decimal(
        1_000_000
    )


@dataclass(frozen=True)
class InstantForecast:
    valid_at: datetime
    value: Decimal | None
    native_resolution_seconds: int = 3600
    native: bool = True


@dataclass(frozen=True)
class AccumulationForecast:
    start_at: datetime
    end_at: datetime
    value: Decimal | None
    native_interval_seconds: int = 3600
    native: bool = True


@dataclass(frozen=True)
class WindMatch:
    sample: InstantForecast
    offset_seconds: Decimal


def match_wind(eta_utc, samples):
    eta = utc_datetime(eta_utc, "checkpoint ETA")
    candidates = []
    for sample in samples:
        instant = utc_datetime(sample.valid_at, "forecast instant")
        if sample.native and sample.native_resolution_seconds == 3600:
            offset = timedelta_decimal_seconds(instant - eta)
            if abs(offset) <= 1800:
                candidates.append((abs(offset), -offset, sample, offset))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:2])
    selected = candidates[0]
    duplicates = [item for item in candidates if item[:2] == selected[:2]]
    value = optional_decimal(selected[2].value)
    if value is None or any(optional_decimal(item[2].value) != value for item in duplicates):
        return None
    return WindMatch(selected[2], selected[3])


def match_hourly_accumulation(eta_utc, samples):
    eta = utc_datetime(eta_utc, "checkpoint ETA")
    matching = []
    for sample in samples:
        start = utc_datetime(sample.start_at, "accumulation start")
        end = utc_datetime(sample.end_at, "accumulation end")
        if end <= start:
            raise DomainValidationError("Accumulation interval must have positive duration")
        if (
            sample.native
            and sample.native_interval_seconds == 3600
            and end - start == timedelta(hours=1)
            and start < eta <= end
        ):
            matching.append(sample)
    if not matching:
        return None
    first = matching[0]
    value = optional_decimal(first.value)
    if value is None:
        return None
    if any(
        (utc_datetime(item.start_at), utc_datetime(item.end_at), optional_decimal(item.value))
        != (utc_datetime(first.start_at), utc_datetime(first.end_at), value)
        for item in matching
    ):
        return None
    return first
