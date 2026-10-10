"""Anonymous examples never grant access to provider execution or private snapshots."""

import hashlib
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.utils import timezone

from atlas.models import AnalysisSnapshot, AssessmentRequestWindow
from atlas.providers.sample import FIXTURE_VERSION
from atlas.services.examples import example_analysis

CODE = "authored-private-access-code-for-tests"
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("public_settings")]


@pytest.fixture
def public_settings():
    with override_settings(
        ATLAS_ASSESSMENT_ACCESS_HASH=hashlib.sha256(CODE.encode()).hexdigest(),
        ATLAS_PUBLIC_EXAMPLES_ENABLED=True,
    ):
        yield


def test_public_shared_curated_result_all_hours_and_no_provider_io():
    client = Client()
    with patch("atlas.services.live.create_live_analysis") as live:
        result = client.get("/api/v1/examples/complete/")
        assert result.status_code == 200
        body = result.json()
        assert body["sample_data"] is True and body["mode"] == "sample"
        assert len(body["routes"]) == 3 and body["recommendation"]["route_id"] == "route-b"
        for _ in range(5):
            assert Client().get("/api/v1/examples/complete/").json()["id"] == body["id"]
        assert AnalysisSnapshot.objects.count() == 1
        assert client.get(f"/api/v1/analyses/{body['id']}/").status_code == 200
        for variable in ("wind", "rain", "snow"):
            for hour in range(49):
                frame = client.get(
                    f"/api/v1/analyses/{body['id']}/frames/?hour={hour}&variable={variable}"
                )
                assert frame.status_code == 200 and frame.json()["hour"] == hour
        live.assert_not_called()


@pytest.mark.parametrize(
    "scenario,state",
    [("complete", "recommended"), ("partial", "unverified"), ("no-travel", "blocked")],
)
def test_curated_scenarios_preserve_domain_outcomes(scenario, state):
    response = Client().get(f"/api/v1/examples/{scenario}/")
    assert response.status_code == 200 and response.json()["recommendation"]["state"] == state


@pytest.mark.parametrize("mode", ["live", "actual", "sample", None, {"mode": "sample"}])
def test_post_mode_never_unlocks_provider_or_private_creation(mode):
    with patch("atlas.services.live.create_live_analysis") as live:
        response = Client().post(
            "/api/v1/analyses/", {"mode": mode}, content_type="application/json"
        )
        assert response.status_code == 401
        live.assert_not_called()
    assert AnalysisSnapshot.objects.count() == 0


@pytest.mark.parametrize("path", ["/api/v1/locations/geocode/", "/api/v1/schema/", "/api/v1/docs/"])
def test_confidential_and_provider_paths_remain_protected(path):
    assert Client().generic("POST" if "geocode" in path else "GET", path).status_code == 401


@pytest.mark.parametrize("mode,marked", [("live", False), ("sample", False), ("live", True)])
def test_uuid_and_marker_do_not_expose_private_or_provider_snapshot(mode, marked):
    snapshot = AnalysisSnapshot.objects.create(
        status="complete",
        expires_at=timezone.now() + timedelta(hours=1),
        public_example_key="complete" if marked else None,
        result={
            "mode": mode,
            "sample_data": mode == "sample",
            "fixture_version": FIXTURE_VERSION,
        },
    )
    for suffix in ("", "frames/?hour=0&variable=wind"):
        assert Client().get(f"/api/v1/analyses/{snapshot.pk}/{suffix}").status_code == 401


def test_expiry_rebuild_bounded_public_cache_and_private_history_not_reclassified():
    old = example_analysis("complete")
    AnalysisSnapshot.objects.filter(pk=old.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    new = example_analysis("complete")
    assert old.pk != new.pk and AnalysisSnapshot.objects.count() == 1
    assert not AnalysisSnapshot.objects.filter(pk=old.pk).exists()


def test_build_and_anonymous_read_caps_durable_fail_closed():
    with override_settings(ATLAS_PUBLIC_READS_PER_MINUTE=1):
        assert Client().get("/api/v1/scenarios/").status_code == 200
        response = Client().get("/api/v1/scenarios/")
        assert response.status_code == 429 and int(response["Retry-After"]) > 0
    with override_settings(ATLAS_PUBLIC_BUILDS_PER_MINUTE=1):
        example_analysis("complete")
        response = Client().get("/api/v1/examples/partial/")
        assert response.status_code == 429
    assert AssessmentRequestWindow.objects.count() <= 3


def test_extra_inputs_on_public_get_rejected_and_no_post_available():
    assert Client().get("/api/v1/examples/complete/?mode=live").status_code == 400
    assert (
        Client().post("/api/v1/examples/complete/", {}, content_type="application/json").status_code
        == 401
    )
    assert AnalysisSnapshot.objects.count() == 0


def test_database_failure_does_not_fall_back_to_unlimited_anonymous_access():
    with patch("atlas.release_access.admit", side_effect=DatabaseError):
        assert Client().get("/api/v1/scenarios/").status_code == 503


def test_private_sample_stays_private_even_with_identical_curated_inputs():
    example = example_analysis("complete")
    headers = {"HTTP_AUTHORIZATION": f"Bearer {CODE}"}
    response = Client().post(
        "/api/v1/analyses/",
        {"mode": "sample", "scenario": "complete", **example.result["inputs"]},
        content_type="application/json",
        **headers,
    )
    assert response.status_code == 201
    identity = response.json()["id"]
    assert AnalysisSnapshot.objects.get(pk=identity).public_example_key is None
    for suffix in ("", "frames/?hour=0&variable=wind"):
        url = f"/api/v1/analyses/{identity}/{suffix}"
        assert Client().get(url).status_code == 401
        assert Client().get(url, **headers).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_visitors_build_one_shared_example():
    if connection.vendor != "postgresql":
        pytest.skip("Requires independent PostgreSQL connections")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    barrier = Barrier(3)

    def visit():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return example_analysis("complete").pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as pool:
        identities = list(pool.map(lambda _: visit(), range(3)))
    assert len(set(identities)) == 1
    assert AnalysisSnapshot.objects.count() == 1
    assert AssessmentRequestWindow.objects.get(pk="public-build").count == 1


def test_public_switch_off_retains_existing_protected_deployment():
    with override_settings(ATLAS_PUBLIC_EXAMPLES_ENABLED=False):
        assert Client().get("/api/v1/scenarios/").status_code == 401
        assert Client().get("/api/v1/examples/complete/").status_code == 401


def test_authorized_schema_documents_public_and_conditional_private_access():
    schema = (
        Client()
        .get(
            "/api/v1/schema/",
            HTTP_AUTHORIZATION=f"Bearer {CODE}",
            HTTP_ACCEPT="application/vnd.oai.openapi+json",
        )
        .json()
    )
    paths = schema["paths"]
    assert paths["/api/v1/examples/{scenario}/"]["get"]["security"] == []
    assert paths["/api/v1/analyses/"]["post"]["security"] == [{"AssessmentReviewer": []}]
    assert paths["/api/v1/analyses/{analysis_id}/"]["get"]["security"] == [
        {},
        {"AssessmentReviewer": []},
    ]


def test_postgresql_completed_access_scope_immutable():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL trigger")
    snapshot = example_analysis("complete")
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalysisSnapshot.objects.filter(pk=snapshot.pk).update(public_example_key=None)
