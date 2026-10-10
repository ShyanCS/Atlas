from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class AtlasError(APIException):
    status_code = 400
    default_code = "VALIDATION_ERROR"

    def __init__(self, code, message, *, status=400, details=None):
        self.status_code = status
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message, code=code)


def exception_handler(exc, context):
    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    if isinstance(exc, RequestDataTooBig):
        return Response(
            {
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": "Request exceeds the 16KiB local limit.",
                    "details": {},
                },
                "request_id": request_id,
            },
            status=413,
        )
    if isinstance(exc, AtlasError):
        return Response(
            {
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
                "request_id": request_id,
            },
            status=exc.status_code,
        )
    response = drf_exception_handler(exc, context)
    if response is None:
        return Response(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "The local sample analysis could not be completed.",
                    "details": {},
                },
                "request_id": request_id,
            },
            status=500,
        )
    codes = {
        400: "VALIDATION_ERROR",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        415: "UNSUPPORTED_MEDIA_TYPE",
        429: "ADMISSION_LIMIT",
    }
    response.data = {
        "error": {
            "code": codes.get(response.status_code, "REQUEST_ERROR"),
            "message": "Request validation failed."
            if response.status_code == 400
            else str(getattr(exc, "detail", "Request could not be completed.")),
            "details": response.data,
        },
        "request_id": request_id,
    }
    return response


def _django_error(request, *, status, code, message):
    return JsonResponse(
        {
            "error": {"code": code, "message": message, "details": {}},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def not_found_view(request, exception):
    return _django_error(
        request, status=404, code="NOT_FOUND", message="This API path does not exist."
    )


def bad_request_view(request, exception):
    return _django_error(
        request, status=400, code="BAD_REQUEST", message="The request could not be accepted."
    )


def server_error_view(request):
    return _django_error(
        request,
        status=500,
        code="INTERNAL_ERROR",
        message="The local API could not complete the request.",
    )
