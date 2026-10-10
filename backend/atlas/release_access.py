"""Shared reviewer bearer code plus bounded database-backed request windows.

This is assessment access control, not user accounts or enterprise identity.
Only fixed window rows exist; user input cannot create arbitrary keys.
"""

import hashlib
import re
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
            not request.path.startswith("/api/")
            or request.path == "/api/v1/health/"
            or request.method == "OPTIONS"
        ):
            return self.get_response(request)
        try:
            public = False
            charged = False
            if settings.ATLAS_PUBLIC_EXAMPLES_ENABLED and request.method in {"GET", "HEAD"}:
                public = request.path == "/api/v1/scenarios/" or bool(
                    re.fullmatch(r"/api/v1/examples/(complete|partial|no-travel)/", request.path)
                )
                match = re.fullmatch(
                    r"/api/v1/analyses/([0-9a-fA-F-]{36})/(frames/)?", request.path
                )
                if match:
                    retry = admit("public-read", settings.ATLAS_PUBLIC_READS_PER_MINUTE)
                    if retry:
                        return denial(
                            request,
                            "PUBLIC_REQUEST_LIMIT",
                            "Too many requests. Try again shortly.",
                            429,
                            retry,
                        )
                    charged = True
                    # Validate UUID before ORM conversion; malformed IDs remain protected.
                    import uuid

                    from atlas.services.examples import public_example_query

                    try:
                        identity = uuid.UUID(match[1])
                    except ValueError:
                        identity = None
                    public = bool(identity and public_example_query().filter(pk=identity).exists())
            if public:
                retry = (
                    None
                    if charged
                    else admit("public-read", settings.ATLAS_PUBLIC_READS_PER_MINUTE)
                )
                if retry:
                    return denial(
                        request,
                        "PUBLIC_REQUEST_LIMIT",
                        "Too many requests. Try again shortly.",
                        429,
                        retry,
                    )
                return self.get_response(request)
        except DatabaseError:
            return denial(
                request,
                "ASSESSMENT_STORAGE_UNAVAILABLE",
                "The workspace is waking or unavailable. Try again shortly.",
                503,
            )
        # Local loopback development retains its explicitly open provider workflow.
        # Hosted startup still mandates the private hash; it cannot use this bypass.
        if not access_hash:
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
                        "This operation is restricted on this deployment. You can explore the example trip.",
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
                    "The request limit was reached. Try again shortly.",
                    429,
                    retry,
                )
        except DatabaseError:
            return denial(
                request,
                "ASSESSMENT_STORAGE_UNAVAILABLE",
                "The workspace is waking or unavailable. Try again shortly.",
                503,
            )
        return self.get_response(request)
