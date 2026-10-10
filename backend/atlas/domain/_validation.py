"""Small validation helpers with no provider, framework or I/O dependencies."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


class DomainValidationError(ValueError):
    """An input cannot support an authoritative domain calculation."""


def optional_decimal(value):
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (Decimal, int, float, str))
    ):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def require_decimal(value, name, *, positive=False):
    number = optional_decimal(value)
    if number is None or (positive and number <= 0):
        raise DomainValidationError(
            f"{name} must be a finite {'positive' if positive else 'nonnegative'} number"
        )
    return number


def utc_datetime(value, name="timestamp"):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone aware")
    return value.astimezone(timezone.utc)
