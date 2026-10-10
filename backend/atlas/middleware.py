import json
import logging
import time
import uuid

from django.http import JsonResponse

logger = logging.getLogger("atlas.requests")


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "event": record.getMessage()
                if record.name.startswith("atlas.")
                else "django_event",
                "request_id": getattr(record, "request_id", None),
                "method": getattr(record, "method", None),
                "status": getattr(record, "status", getattr(record, "status_code", None)),
                "duration_ms": getattr(record, "duration_ms", None),
            }
        )


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        try:
            request.request_id = str(uuid.UUID(supplied))
        except (ValueError, AttributeError):
            request.request_id = str(uuid.uuid4())
        started = time.monotonic()
        content_length = request.META.get("CONTENT_LENGTH", "0")
        if content_length.isdigit() and int(content_length) > 16 * 1024:
            response = JsonResponse(
                {
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "Request exceeds the 16KiB local limit.",
                        "details": {},
                    },
                    "request_id": request.request_id,
                },
                status=413,
            )
        else:
            response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        response["Cache-Control"] = "no-store"
        logger.info(
            "http_request",
            extra={
                "request_id": request.request_id,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response
