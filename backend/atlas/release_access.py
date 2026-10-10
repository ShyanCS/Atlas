"""Shared reviewer bearer code plus bounded database-backed request windows.

This is assessment access control, not user accounts or enterprise identity.
Only three constant window rows exist; user input cannot create arbitrary keys.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.utils import timezone

from atlas.models import AssessmentRequestWindow


def admit(key, cap):
    now = timezone.now()
    with transaction.atomic():
        AssessmentRequestWindow.objects.get_or_create(id=key, defaults={"started_at": now})
        window = AssessmentRequestWindow.objects.select_for_update().get(pk=key)
        if now >= window.started_at + timedelta(minutes=1):
            window.started_at, window.count = now, 0
        if window.count >= cap:
            return max(1, int((window.started_at + timedelta(minutes=1) - now).total_seconds()))
        window.count += 1
        window.save(update_fields=["started_at", "count"])
    return None


def denial(request, code, message, status, retry=None):
    response = JsonResponse(
        {
            "error": {"code": code, "message": message, "details": {}},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )
    if status == 401:
        response["WWW-Authenticate"] = 'Bearer realm="Spotter Atlas assessment"'
    if retry:
        response["Retry-After"] = str(retry)
    return response


class AssessmentAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        access_hash = settings.ATLAS_ASSESSMENT_ACCESS_HASH
        if (
            not access_hash
            or not request.path.startswith("/api/")
            or request.path == "/api/v1/health/"
            or request.method == "OPTIONS"
        ):
            return self.get_response(request)
        authorization = request.headers.get("Authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        valid = 24 <= len(token) <= 256 and secrets.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(), access_hash
        )
        try:
            if not valid:
                retry = admit("auth", settings.ATLAS_AUTH_FAILURES_PER_MINUTE)
                return (
                    denial(
                        request, "ASSESSMENT_THROTTLED", "Access attempts are limited.", 429, retry
                    )
                    if retry
                    else denial(
                        request,
                        "ASSESSMENT_ACCESS_REQUIRED",
                        "Enter the private reviewer access code.",
                        401,
                    )
                )
            write = request.method not in ("GET", "HEAD")
            retry = admit(
                "write" if write else "read",
                settings.ATLAS_WRITE_REQUESTS_PER_MINUTE
                if write
                else settings.ATLAS_READ_REQUESTS_PER_MINUTE,
            )
            if retry:
                return denial(
                    request,
                    "ASSESSMENT_THROTTLED",
                    "The assessment request limit was reached. No provider retry was made.",
                    429,
                    retry,
                )
        except DatabaseError:
            return denial(
                request,
                "ASSESSMENT_STORAGE_UNAVAILABLE",
                "The assessment database is waking or unavailable. No provider request was made.",
                503,
            )
        return self.get_response(request)
