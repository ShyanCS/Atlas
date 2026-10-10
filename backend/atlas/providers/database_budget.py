"""Durable finite attempts. No network I/O inside a database transaction."""

import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.utils import timezone

from atlas.models import ProviderRequestBudget
from atlas.providers.tomtom_http import ProviderError

BUDGET_ID = "assessment-v1"
DEFAULT_CAPS = {"routing": 8, "geocoding": 12, "weather": 64}


class DatabaseAssessmentBudget:
    @contextmanager
    def claim(self, operation):
        lease = uuid.uuid4()
        now = timezone.now()
        try:
            with transaction.atomic():
                budget = ProviderRequestBudget.objects.select_for_update(nowait=True).get(
                    pk=BUDGET_ID
                )
                if operation not in DEFAULT_CAPS or any(
                    type(budget.counts.get(k)) is not int
                    or budget.counts[k] < 0
                    or type(budget.caps.get(k)) is not int
                    or not 0 <= budget.caps[k] <= DEFAULT_CAPS[k]
                    for k in DEFAULT_CAPS
                ):
                    raise ProviderError("BUDGET_STORAGE_INVALID")
                if budget.stop_code:
                    raise ProviderError(budget.stop_code)
                if budget.lease_expires_at and budget.lease_expires_at > now:
                    raise ProviderError("PROVIDER_BUSY")
                if budget.counts[operation] >= budget.caps[operation]:
                    raise ProviderError("ASSESSMENT_REQUEST_CAP")
                budget.counts[operation] += 1
                budget.lease_id = lease
                budget.lease_expires_at = now + timedelta(seconds=120)
                budget.save(update_fields=["counts", "lease_id", "lease_expires_at"])
        except ProviderRequestBudget.DoesNotExist:
            raise ProviderError("PROVIDER_BUDGET_NOT_INITIALIZED") from None
        except DatabaseError:
            raise ProviderError("PROVIDER_BUDGET_STORAGE_UNAVAILABLE") from None
        stop = None
        try:
            yield
        except ProviderError as error:
            if error.status in (401, 403, 429):
                stop = error.code
            raise
        finally:
            try:
                with transaction.atomic():
                    budget = ProviderRequestBudget.objects.select_for_update().get(pk=BUDGET_ID)
                    if stop:
                        budget.stop_code = stop
                    if budget.lease_id == lease:
                        budget.lease_id = None
                        budget.lease_expires_at = None
                    budget.save(update_fields=["stop_code", "lease_id", "lease_expires_at"])
            except (DatabaseError, ProviderRequestBudget.DoesNotExist):
                # Debit was committed before I/O. Never continue with a local fallback.
                raise ProviderError("PROVIDER_BUDGET_STORAGE_UNAVAILABLE") from None
