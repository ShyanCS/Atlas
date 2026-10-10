"""Short-lived snapshots and bounded assessment admission/attempt counters."""

import uuid

from django.db import models


class AnalysisSnapshot(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        COMPLETE = "complete"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(db_index=True)
    result = models.JSONField(default=dict)
    frame_data = models.JSONField(default=dict)


class ProviderRequestBudget(models.Model):
    id = models.CharField(primary_key=True, max_length=40)
    counts = models.JSONField(default=dict)
    caps = models.JSONField(default=dict)
    stop_code = models.CharField(max_length=80, blank=True)
    lease_id = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)


class AssessmentRequestWindow(models.Model):
    id = models.CharField(primary_key=True, max_length=16)
    started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
