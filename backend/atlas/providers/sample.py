"""Original illustrative data, authored for tests; no provider-derived geometry."""

from decimal import Decimal
from typing import Mapping

from atlas.domain import GeoPoint, ProgressAnchor, miles_to_meters
from atlas.providers.interfaces import (
    ProviderCapabilities,
    SampleRouteValues,
    SampleScenario,
    SampleWeatherValues,
)

FIXTURE_VERSION = "atlas-authored-sample-v2"


class SampleRoutingProvider:
    """Authored scenario source implementing SampleRoutingFixture, not the live port."""

    capabilities = ProviderCapabilities("authored-sample", False, True, True)

    def candidates(self, inputs: Mapping[str, object]) -> tuple[SampleRouteValues, ...]:
        # Deliberately schematic, straight geographic legs; not road navigation.
        definitions = (
            (
                "route-a",
                "A",
                "790",
                708 * 60,
                [
                    (41.8781, -87.6298),
                    (40.7, -88.2),
                    (39.4, -87.6),
                    (38.0, -86.9),
                    (36.8, -86.4),
                    (35.5, -85.2),
                    (33.749, -84.388),
                ],
            ),
            (
                "route-b",
                "B",
                "812",
                744 * 60,
                [
                    (41.8781, -87.6298),
                    (41.1, -85.6),
                    (40.0, -84.0),
                    (38.7, -83.4),
                    (37.1, -83.2),
                    (35.4, -84.2),
                    (33.749, -84.388),
                ],
            ),
            (
                "route-c",
                "C",
                "774",
                689 * 60,
                [
                    (41.8781, -87.6298),
                    (40.9, -87.3),
                    (39.7, -86.3),
                    (38.5, -85.5),
                    (37.0, -85.1),
                    (35.6, -84.7),
                    (33.749, -84.388),
                ],
            ),
        )
        candidates: list[SampleRouteValues] = []
        time_fractions = (
            Decimal("0"),
            Decimal("0.13"),
            Decimal("0.32"),
            Decimal("0.48"),
            Decimal("0.64"),
            Decimal("0.83"),
            Decimal("1"),
        )
        distance_fractions = (
            Decimal("0"),
            Decimal("0.16"),
            Decimal("0.31"),
            Decimal("0.49"),
            Decimal("0.65"),
            Decimal("0.84"),
            Decimal("1"),
        )
        for index, (route_id, code, miles, duration, pairs) in enumerate(definitions):
            distance = miles_to_meters(Decimal(miles))
            points = tuple(GeoPoint(lat, lon) for lat, lon in pairs)
            anchors = tuple(
                ProgressAnchor(
                    i, distance * distance_fractions[i], Decimal(duration) * time_fractions[i]
                )
                for i in range(len(points))
            )
            candidates.append(
                {
                    "id": route_id,
                    "code": code,
                    "label": {
                        "A": "Illustrated western arc",
                        "B": "Illustrated eastern arc",
                        "C": "Illustrated central arc",
                    }[code],
                    "candidate_index": index,
                    "points": points,
                    "anchors": anchors,
                    "distance_m": distance,
                    "duration_seconds": Decimal(duration),
                }
            )
        return tuple(candidates)


def pulse(fraction: Decimal, center: str, width: str) -> Decimal:
    return max(Decimal(0), Decimal(1) - abs(fraction - Decimal(center)) / Decimal(width))


class SampleWeatherProvider:
    """Authored scenario source implementing SampleWeatherFixture, not a location API."""

    def checkpoint_observation(
        self,
        *,
        route_index: int,
        fraction: Decimal,
        elapsed_hours: Decimal,
        scenario: SampleScenario,
    ) -> SampleWeatherValues:
        fraction = Decimal(str(fraction))
        elapsed_hours = Decimal(str(elapsed_hours))
        if route_index == 0:
            wind = Decimal("24") + Decimal("18") * pulse(fraction, ".45", ".28")
            rain = Decimal(".03") + Decimal(".31") * pulse(fraction, ".70", ".20")
            snow = Decimal(".12") + Decimal("1.4") * pulse(fraction, ".22", ".16")
        elif route_index == 1:
            wind = Decimal("20") + Decimal("11") * pulse(fraction, ".45", ".30")
            rain = Decimal(".02") + Decimal(".16") * pulse(fraction, ".65", ".23")
            snow = Decimal(".05") + Decimal(".9") * pulse(fraction, ".35", ".20")
        else:
            wind = Decimal("25") + Decimal("25") * pulse(fraction, ".55", ".33")
            rain = Decimal(".02") + Decimal(".63") * pulse(fraction, ".60", ".20")
            snow = Decimal(".1") + Decimal("2.7") * pulse(fraction, ".40", ".23")
        if scenario == "no-travel" and Decimal(".25") <= fraction <= Decimal(".75"):
            wind = Decimal("60")
        if scenario == "partial" and elapsed_hours >= Decimal("6"):
            snow = None
        # An explicit illustrative finite source window, not NOAA coverage.
        if elapsed_hours > Decimal("24"):
            snow = None
        return {"wind": wind, "rain": rain, "snow": snow}
