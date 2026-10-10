"""Assessment JSON weather boundary. No native-depth or native-model-run claim.

Provider hourly slots are explicitly accepted by assessment source policy v1.
Domain matchers operate on accepted normalized slots; physical source resolution
is UNKNOWN and never described as native. No temperature/phase/SWE rain inference.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from atlas.domain import (
    AccumulationForecast,
    DomainValidationError,
    GeoPoint,
    InstantForecast,
    geodesic_distance_m,
    match_hourly_accumulation,
    match_wind,
)
from atlas.providers.interfaces import WeatherMeasurement
from atlas.providers.tomtom_http import ProviderError

SOURCE_POLICY = "open-meteo-noncommercial-assessment-v1"
MODEL = "icon_global"
FIELDS = ("wind_speed_10m", "rain", "showers", "snowfall")
FLAGS = (
    "ASSESSMENT_ONLY_NONCOMMERCIAL",
    "PROVIDER_HOURLY_SERVICE_SLOTS_NOT_VERIFIED_NATIVE_INTERVALS",
    "MODEL_RUN_NOT_EXPOSED_BY_FORECAST_API",
    "LATEST_RUNS_MAY_BE_STITCHED_BY_PROVIDER",
)


def point_key(point):
    return (point.latitude, point.longitude)


def valid_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except Exception:
        return None


class OpenMeteoAdapter:
    def __init__(self, transport, *, accept_provider_snowfall=False):
        self.transport = transport
        self.accept_provider_snowfall = accept_provider_snowfall

    def measurements(self, query):
        if not 1 <= len(query.points) <= 20:
            raise ProviderError("WEATHER_BATCH_LIMIT")
        if (
            query.start_at.tzinfo is None
            or query.end_at.tzinfo is None
            or query.end_at <= query.start_at
            or query.end_at - query.start_at > timedelta(days=6)
        ):
            raise ProviderError("WEATHER_WINDOW_INVALID")
        start = query.start_at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        end = query.end_at.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
        payload = self.transport.get_json(
            [
                ("latitude", ",".join(str(p.latitude) for p in query.points)),
                ("longitude", ",".join(str(p.longitude) for p in query.points)),
                ("hourly", ",".join(FIELDS)),
                ("models", MODEL),
                ("timezone", "GMT"),
                ("timeformat", "unixtime"),
                ("wind_speed_unit", "mph"),
                ("precipitation_unit", "inch"),
                ("start_hour", start.strftime("%Y-%m-%dT%H:%M")),
                ("end_hour", end.strftime("%Y-%m-%dT%H:%M")),
            ]
        )
        fetched = datetime.now(timezone.utc)
        records = payload if isinstance(payload, list) else [payload]
        if len(records) != len(query.points):
            raise ProviderError("WEATHER_LOCATION_COUNT_MISMATCH")
        output = []
        for index, (point, raw) in enumerate(zip(query.points, records)):
            try:
                units, hourly = raw["hourly_units"], raw["hourly"]
                if raw["utc_offset_seconds"] != 0 or any(
                    units.get(field) != ("mp/h" if field == "wind_speed_10m" else "inch")
                    for field in FIELDS
                ):
                    raise ValueError
                source = GeoPoint(raw["latitude"], raw["longitude"])
                if geodesic_distance_m(point, source) > 50_000 or (
                    "location_id" in raw and raw["location_id"] != index
                ):
                    raise ValueError
                times = hourly["time"]
                if not times or len(times) > 146 or any(type(t) is not int for t in times):
                    raise ValueError
                if any(b - a != 3600 for a, b in zip(times, times[1:])):
                    raise ValueError
                if any(
                    not isinstance(hourly.get(f), list) or len(hourly[f]) != len(times)
                    for f in FIELDS
                ):
                    raise ValueError
                if any(t % 3600 for t in times):
                    raise ValueError
            except (KeyError, TypeError, ValueError, DomainValidationError):
                raise ProviderError("WEATHER_CONTRACT_INVALID") from None
            for i, timestamp in enumerate(times):
                valid = datetime.fromtimestamp(timestamp, timezone.utc)
                rain, showers = valid_number(hourly["rain"][i]), valid_number(hourly["showers"][i])
                values = {
                    "wind": valid_number(hourly["wind_speed_10m"][i]),
                    "rain": rain + showers if rain is not None and showers is not None else None,
                    "snow": valid_number(hourly["snowfall"][i])
                    if self.accept_provider_snowfall
                    else None,
                }
                for variable, value in values.items():
                    flags = FLAGS + (
                        ("PROVIDER_SNOWFALL_FIXED_7_TO_1_RELATIONSHIP",)
                        if variable == "snow"
                        else ()
                    )
                    if variable == "rain":
                        flags += ("LIQUID_RAIN_PLUS_CONVECTIVE_SHOWERS",)
                    output.append(
                        WeatherMeasurement(
                            point,
                            variable,
                            value,
                            "mph" if variable == "wind" else "in",
                            {
                                "provider_id": "open-meteo",
                                "model_id": MODEL,
                                "model_run_at": None,
                                "retrieved_at": fetched,
                                "source_point": source,
                                "valid_at": valid,
                                "interval_start": valid - timedelta(hours=1)
                                if variable != "wind"
                                else None,
                                "interval_end": valid if variable != "wind" else None,
                                "native_interval_seconds": None,
                                "native": False,
                                "missing_reason": "PROVIDER_SNOWFALL_NOT_APPROVED"
                                if variable == "snow" and not self.accept_provider_snowfall
                                else "PROVIDER_VALUE_MISSING_OR_INVALID"
                                if value is None
                                else None,
                                "quality_flags": flags,
                            },
                        )
                    )
        return tuple(output)


def select_measurements(records, requested_at):
    """Retain canonical (start,end] / nearest wind matching on approved service slots."""
    values, outputs = {}, {}
    for variable in ("wind", "rain", "snow"):
        options = [m for m in records if m.variable == variable]
        if variable == "wind":
            matched = match_wind(
                requested_at,
                tuple(InstantForecast(m.provenance["valid_at"], m.value) for m in options),
            )
            instant = matched.sample.valid_at if matched else None
            selected = next((m for m in options if m.provenance["valid_at"] == instant), None)
        else:
            slots = tuple(
                AccumulationForecast(
                    m.provenance["interval_start"], m.provenance["interval_end"], m.value
                )
                for m in options
            )
            matched = match_hourly_accumulation(requested_at, slots)
            selected = (
                next((m for m in options if m.provenance["interval_end"] == matched.end_at), None)
                if matched
                else None
            )
        # Null matching interval retains source time and the provider's missing reason.
        if selected is None:
            selected = next(
                (
                    m
                    for m in options
                    if (
                        m.provenance["interval_start"] is not None
                        and m.provenance["interval_start"]
                        < requested_at
                        <= m.provenance["interval_end"]
                    )
                    or (
                        variable == "wind"
                        and abs((m.provenance["valid_at"] - requested_at).total_seconds()) <= 1800
                    )
                ),
                None,
            )
        value = selected.value if matched and selected else None
        provenance = selected.provenance if selected else None
        values[variable] = value

        def stamp(value):
            return value.isoformat().replace("+00:00", "Z") if value else None

        outputs[variable] = {
            "value": str(value) if value is not None else None,
            "unit": "mph" if variable == "wind" else "in/hour",
            "missing_reason": None
            if value is not None
            else (
                provenance["missing_reason"]
                if provenance and provenance["missing_reason"]
                else "FORECAST_TIME_UNAVAILABLE"
            ),
            "provenance": {
                "kind": "forecast",
                "source": "Open-Meteo / DWD ICON Global (CC BY 4.0)",
                "model": MODEL,
                "model_run_at": None,
                "valid_at": stamp(provenance["valid_at"]) if provenance else None,
                "interval_start": stamp(provenance["interval_start"]) if provenance else None,
                "interval_end": stamp(provenance["interval_end"]) if provenance else None,
                "native_interval_seconds": None,
                "retrieved_at": stamp(provenance["retrieved_at"])
                if provenance
                else stamp(datetime.now(timezone.utc)),
                "quality_flags": list(provenance["quality_flags"] if provenance else FLAGS),
                "source_point": {
                    "latitude": str(provenance["source_point"].latitude),
                    "longitude": str(provenance["source_point"].longitude),
                }
                if provenance
                else None,
                "source_policy": SOURCE_POLICY,
            },
        }
    return values, outputs
