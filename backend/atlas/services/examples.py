"""Three shared curated examples. No user input, arbitrary variants or provider I/O."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from atlas.api.errors import AtlasError
from atlas.api.serializers import SAMPLE_DESTINATION, SAMPLE_ORIGIN, AnalysisInputSerializer
from atlas.models import AnalysisSnapshot, AssessmentRequestWindow
from atlas.providers.sample import FIXTURE_VERSION
from atlas.release_access import admit
from atlas.services.analysis import create_analysis

SCENARIOS = frozenset({"complete", "partial", "no-travel"})


def public_example_query():
    # A marker alone cannot expose a provider/private/failed/older-contract snapshot.
    return AnalysisSnapshot.objects.filter(
        public_example_key__in=SCENARIOS,
        status="complete",
        result__mode="sample",
        result__sample_data=True,
        result__fixture_version=FIXTURE_VERSION,
    )


def example_analysis(scenario):
    if not settings.ATLAS_PUBLIC_EXAMPLES_ENABLED:
        raise AtlasError(
            "EXAMPLES_UNAVAILABLE", "Example routes are not available here.", status=503
        )
    if scenario not in SCENARIOS:
        raise AtlasError("EXAMPLE_NOT_FOUND", "Choose an available example route.", status=404)
    # Serialize cache creation across workers using one fixed database row. All work
    # inside this transaction is bounded, local computation; never external I/O.
    with transaction.atomic():
        row, _ = AssessmentRequestWindow.objects.get_or_create(
            id="example-build", defaults={"started_at": timezone.now()}
        )
        AssessmentRequestWindow.objects.select_for_update().get(pk=row.pk)
        snapshot = (
            public_example_query().filter(public_example_key=scenario).defer("frame_data").first()
        )
        if snapshot and snapshot.expires_at > timezone.now():
            return snapshot
        retry = admit("public-build", settings.ATLAS_PUBLIC_BUILDS_PER_MINUTE)
        if retry:
            raise AtlasError(
                "EXAMPLES_BUSY", "Example routes are loading. Try again shortly.", status=429
            )
        AnalysisSnapshot.objects.filter(public_example_key=scenario).delete()
        serializer = AnalysisInputSerializer(
            data={
                "mode": "sample",
                "scenario": scenario,
                "origin": SAMPLE_ORIGIN,
                "destination": SAMPLE_DESTINATION,
                "departure_at": "2026-10-10T11:00:00Z",
                "origin_timezone": "America/Chicago",
                "load_weight_lb": "24000",
                "checkpoint_interval_miles": 25,
            }
        )
        serializer.is_valid(raise_exception=True)
        return create_analysis(serializer.validated_data, public_example_key=scenario)
