"""Deployment controls, durable budgets and PostgreSQL integrity. No provider I/O."""

import hashlib
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client, override_settings
from django.utils import timezone

from atlas.models import AnalysisSnapshot, AssessmentRequestWindow, ProviderRequestBudget
from atlas.providers.assessment_http import DeadlineBudget
from atlas.providers.database_budget import BUDGET_ID, DatabaseAssessmentBudget
from atlas.providers.tomtom_http import ProviderError
from atlas.services.live import live_available
from config.database import database_config, hosted_mode

CODE = "authored-reviewer-code-for-unit-tests"
ACCESS_HASH = hashlib.sha256(CODE.encode()).hexdigest()
pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "mode,render,expected",
    [("local", "true", True), (None, "true", True), ("local", "", False), ("hosted", "", True)],
)
def test_render_cannot_bypass_hosted_protections_with_local_default(mode, render, expected):
    values = {"RENDER": render}
    if mode is not None:
        values["ATLAS_DEPLOYMENT"] = mode
    assert hosted_mode(values) == expected


def test_mistyped_deployment_mode_fails_closed():
    with pytest.raises(ImproperlyConfigured):
        hosted_mode({"ATLAS_DEPLOYMENT": "hostedd"})


def initialize():
    call_command("initialize_assessment_budget", verbosity=0)
    return DatabaseAssessmentBudget()


def test_database_cap_survives_new_objects_connections_and_initialization():
    budget = initialize()
    for _ in range(8):
        with budget.claim("routing"):
            pass
    call_command("initialize_assessment_budget", verbosity=0)
    with pytest.raises(ProviderError, match="ASSESSMENT_REQUEST_CAP"):
        with DatabaseAssessmentBudget().claim("routing"):
            pytest.fail("I/O must never begin beyond cap")
    assert ProviderRequestBudget.objects.get(pk=BUDGET_ID).counts["routing"] == 8


def test_database_budget_failed_attempt_debited_and_quota_latched():
    budget = initialize()
    with pytest.raises(ProviderError, match="PROVIDER_QUOTA"):
        with budget.claim("weather"):
            raise ProviderError("PROVIDER_QUOTA", status=429)
    with pytest.raises(ProviderError, match="PROVIDER_QUOTA"):
        with DatabaseAssessmentBudget().claim("geocoding"):
            pytest.fail("No I/O after quota stop")
    stored = ProviderRequestBudget.objects.get(pk=BUDGET_ID)
    assert stored.counts["weather"] == 1 and stored.lease_id is None


def test_budget_requires_explicit_initialization_and_rejects_corruption():
    with pytest.raises(ProviderError, match="PROVIDER_BUDGET_NOT_INITIALIZED"):
        with DatabaseAssessmentBudget().claim("routing"):
            pass
    initialize()
    ProviderRequestBudget.objects.filter(pk=BUDGET_ID).update(counts={"routing": True})
    with pytest.raises(ProviderError, match="BUDGET_STORAGE_INVALID"):
        with DatabaseAssessmentBudget().claim("routing"):
            pass


def test_lease_prevents_parallel_request_and_crash_recovery_never_refunds():
    budget = initialize()
    with budget.claim("routing"):
        with pytest.raises(ProviderError, match="PROVIDER_BUSY"):
            with DatabaseAssessmentBudget().claim("weather"):
                pass
    row = ProviderRequestBudget.objects.get(pk=BUDGET_ID)
    import uuid

    row.lease_id, row.lease_expires_at = uuid.uuid4(), timezone.now() - timedelta(seconds=1)
    row.save()
    with DatabaseAssessmentBudget().claim("weather"):
        pass
    assert ProviderRequestBudget.objects.get(pk=BUDGET_ID).counts["routing"] == 1


def test_deadline_never_starts_io_after_expiry(monkeypatch):
    inner = Mock()
    with pytest.raises(ProviderError, match="PROVIDER_ACQUISITION_TIMEOUT"):
        with DeadlineBudget(inner, -1).claim("routing"):
            pass
    inner.claim.assert_not_called()


def test_expired_snapshot_purge_preserves_current_result_and_durable_budget():
    budget = initialize()
    with budget.claim("routing"):
        pass
    expired = AnalysisSnapshot.objects.create(
        status="complete", expires_at=timezone.now() - timedelta(seconds=1)
    )
    current = AnalysisSnapshot.objects.create(
        status="complete", expires_at=timezone.now() + timedelta(hours=1)
    )
    call_command("purge_expired_analyses")
    assert not AnalysisSnapshot.objects.filter(pk=expired.pk).exists()
    assert AnalysisSnapshot.objects.filter(pk=current.pk).exists()
    assert ProviderRequestBudget.objects.get(pk=BUDGET_ID).counts["routing"] == 1


@override_settings(ATLAS_ASSESSMENT_ACCESS_HASH=ACCESS_HASH)
def test_reviewer_access_health_preflight_and_credential_free_samples():
    client = Client()
    health = client.get("/api/v1/health/").json()
    assert health["assessment_access_required"] is True and health["live_available"] is False
    assert client.get("/api/v1/scenarios/").status_code == 401
    assert client.get("/api/v1/schema/").status_code == 401
    assert client.options("/api/v1/scenarios/").status_code == 200
    response = client.get("/api/v1/scenarios/", HTTP_AUTHORIZATION=f"Bearer {CODE}")
    assert response.status_code == 200 and response.json()["sample_data"] is True
    assert "Cache-Control" in response and response["Cache-Control"] == "no-store"


@override_settings(ATLAS_ASSESSMENT_ACCESS_HASH=ACCESS_HASH, ATLAS_READ_REQUESTS_PER_MINUTE=2)
def test_read_throttle_survives_clients_and_resets_only_after_window():
    for _ in range(2):
        assert (
            Client().get("/api/v1/scenarios/", HTTP_AUTHORIZATION=f"Bearer {CODE}").status_code
            == 200
        )
    limited = Client().get("/api/v1/scenarios/", HTTP_AUTHORIZATION=f"Bearer {CODE}")
    assert limited.status_code == 429 and int(limited["Retry-After"]) > 0
    AssessmentRequestWindow.objects.filter(pk="read").update(
        started_at=timezone.now() - timedelta(minutes=2)
    )
    assert (
        Client().get("/api/v1/scenarios/", HTTP_AUTHORIZATION=f"Bearer {CODE}").status_code == 200
    )


@override_settings(ATLAS_ASSESSMENT_ACCESS_HASH=ACCESS_HASH, ATLAS_AUTH_FAILURES_PER_MINUTE=1)
def test_access_failures_bounded_and_secret_never_echoed():
    response = Client().get("/api/v1/scenarios/", HTTP_AUTHORIZATION="Bearer secret-private-value")
    assert response.status_code == 401 and b"secret-private-value" not in response.content
    assert Client().get("/api/v1/scenarios/").status_code == 429
    assert AssessmentRequestWindow.objects.count() == 1


@override_settings(
    ATLAS_ASSESSMENT_ACCESS_HASH=ACCESS_HASH,
    ATLAS_CORS_ORIGINS=["https://atlas.pages.dev"],
    CORS_ALLOWED_ORIGINS=["https://atlas.pages.dev"],
)
def test_exact_origin_cors_and_bearer_preflight():
    client = Client()
    response = client.options(
        "/api/v1/analyses/",
        HTTP_ORIGIN="https://atlas.pages.dev",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
    )
    assert response["Access-Control-Allow-Origin"] == "https://atlas.pages.dev"
    assert "authorization" in response["Access-Control-Allow-Headers"]
    assert "Access-Control-Allow-Credentials" not in response
    denied = client.options(
        "/api/v1/analyses/",
        HTTP_ORIGIN="https://attacker.invalid",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert "Access-Control-Allow-Origin" not in denied


@pytest.mark.parametrize(
    "weather,tomtom", [(False, False), (True, False), (False, True), (True, True)]
)
def test_public_live_permission_switches_fail_closed(weather, tomtom):
    with override_settings(
        ATLAS_HOSTED=True,
        ATLAS_LIVE_ENABLED=True,
        ATLAS_NONCOMMERCIAL_ASSESSMENT=True,
        ATLAS_ACCEPT_PROVIDER_SNOWFALL=True,
        ATLAS_TOMTOM_KEY="authored-key",
        ATLAS_PUBLIC_WEATHER_CONFIRMED=weather,
        ATLAS_PUBLIC_TOMTOM_CONFIRMED=tomtom,
    ):
        assert live_available() == (weather and tomtom)


def test_postgres_configuration_pooling_tls_and_safe_errors():
    config = database_config(
        "postgresql://user:private%40value@db-pooler.neon.tech/neondb", hosted=True
    )
    assert config["OPTIONS"]["sslmode"] == "verify-full"
    assert config["OPTIONS"]["sslrootcert"] == "system"
    assert config["OPTIONS"]["prepare_threshold"] is None
    assert config["CONN_MAX_AGE"] == 0 and config["DISABLE_SERVER_SIDE_CURSORS"]
    for bad in [
        "sqlite:///secret",
        "postgresql://u:secret@host/db?sslmode=disable",
        "postgresql://u:secret@host/db?sslmode=require",
    ]:
        with pytest.raises(ImproperlyConfigured) as error:
            database_config(bad, hosted=True)
        assert "secret" not in str(error.value)


@pytest.mark.django_db(transaction=True)
def test_postgresql_published_snapshot_is_immutable_and_survives_reconnect():
    if connection.vendor != "postgresql":
        pytest.skip("Requires actual PostgreSQL trigger/connection")
    snapshot = AnalysisSnapshot.objects.create(
        status="complete",
        expires_at=timezone.now() + timedelta(hours=1),
        result={"published": True},
        frame_data={"49": True},
    )
    close_old_connections()
    assert AnalysisSnapshot.objects.get(pk=snapshot.pk).result == {"published": True}
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalysisSnapshot.objects.filter(pk=snapshot.pk).update(result={"published": False})
    assert AnalysisSnapshot.objects.get(pk=snapshot.pk).result == {"published": True}


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_lease_and_restart_cap():
    if connection.vendor != "postgresql":
        pytest.skip("Requires real independent PostgreSQL connections")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    budget = initialize()
    entered, release = Event(), Event()

    def worker():
        close_old_connections()
        with budget.claim("routing"):
            entered.set()
            assert release.wait(5)
        close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert entered.wait(5)
            with pytest.raises(ProviderError, match="PROVIDER_BUSY"):
                with DatabaseAssessmentBudget().claim("routing"):
                    pass
        finally:
            release.set()
        future.result()
    close_old_connections()
    call_command("initialize_assessment_budget")
    assert ProviderRequestBudget.objects.get(pk=BUDGET_ID).counts["routing"] == 1
