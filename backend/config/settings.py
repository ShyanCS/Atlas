"""Local defaults and explicit fail-closed hosted assessment configuration."""

import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.database import database_config, hosted_mode

BASE_DIR = Path(__file__).resolve().parent.parent
ATLAS_HOSTED = hosted_mode(os.environ)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(64)
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
if ATLAS_HOSTED:
    if not os.environ.get("DJANGO_SECRET_KEY") or len(SECRET_KEY) < 50 or DEBUG:
        raise ImproperlyConfigured(
            "Hosted mode requires a stable 50+ character secret and DEBUG=0."
        )
    ALLOWED_HOSTS = os.environ.get(
        "DJANGO_ALLOWED_HOSTS", os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    ).split(",")
    if any(not h or "*" in h or ":" in h or "/" in h or h.startswith(".") for h in ALLOWED_HOSTS):
        raise ImproperlyConfigured(
            "Set exact hosted Django hostnames, without schemes or wildcards."
        )
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "atlas.apps.AtlasConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "atlas.middleware.RequestContextMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "atlas.release_access.AssessmentAccessMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("ATLAS_SQLITE_PATH", str(BASE_DIR / "atlas.sqlite3")),
        "OPTIONS": {"timeout": 10},
    }
}
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": database_config(os.environ["DATABASE_URL"], hosted=ATLAS_HOSTED)}
elif ATLAS_HOSTED:
    raise ImproperlyConfigured("Hosted mode requires DATABASE_URL; SQLite fallback is disabled.")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
CORS_ALLOWED_ORIGINS = os.environ.get(
    "ATLAS_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
).split(",")
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = ["accept", "content-type", "x-request-id", "authorization"]
CORS_EXPOSE_HEADERS = ["X-Request-ID"]
ATLAS_ASSESSMENT_ACCESS_HASH = os.environ.get("ATLAS_ASSESSMENT_ACCESS_HASH", "")
if ATLAS_HOSTED:
    import re

    if not re.fullmatch(r"[a-f0-9]{64}", ATLAS_ASSESSMENT_ACCESS_HASH):
        raise ImproperlyConfigured("Hosted mode requires a SHA-256 reviewer access-code hash.")
    if not os.environ.get("ATLAS_CORS_ORIGINS") or any(
        not origin.startswith("https://") or "*" in origin for origin in CORS_ALLOWED_ORIGINS
    ):
        raise ImproperlyConfigured("Hosted mode requires explicit HTTPS frontend CORS origins.")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if ATLAS_HOSTED else None
SECURE_SSL_REDIRECT = ATLAS_HOSTED
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
SECURE_HSTS_SECONDS = 3600 if ATLAS_HOSTED else 0
# The shared managed hostname does not imply authority to preload subdomains.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = ATLAS_HOSTED
CSRF_COOKIE_SECURE = ATLAS_HOSTED
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS if ATLAS_HOSTED else []
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
ATLAS_SNAPSHOT_RETENTION_HOURS = min(
    168,
    max(1, int(os.environ.get("ATLAS_SNAPSHOT_RETENTION_HOURS", "1" if ATLAS_HOSTED else "24"))),
)
ATLAS_MAX_LOCAL_SNAPSHOTS = min(
    1000, max(1, int(os.environ.get("ATLAS_MAX_LOCAL_SNAPSHOTS", "20" if ATLAS_HOSTED else "100")))
)
ATLAS_LIVE_ENABLED = os.environ.get("ATLAS_LIVE_ENABLED", "0") == "1"
ATLAS_NONCOMMERCIAL_ASSESSMENT = os.environ.get("ATLAS_NONCOMMERCIAL_ASSESSMENT", "0") == "1"
ATLAS_ACCEPT_PROVIDER_SNOWFALL = os.environ.get("ATLAS_ACCEPT_PROVIDER_SNOWFALL", "0") == "1"
ATLAS_PROVIDER_BUDGET_PATH = os.environ.get(
    "ATLAS_PROVIDER_BUDGET_PATH", str(BASE_DIR / ".local-provider-budget.json")
)
ATLAS_CA_BUNDLE = os.environ.get("ATLAS_CA_BUNDLE")
ATLAS_TOMTOM_KEY = os.environ.get("TOMTOM_API_KEY", "")
ATLAS_PUBLIC_WEATHER_CONFIRMED = os.environ.get("ATLAS_PUBLIC_WEATHER_CONFIRMED", "0") == "1"
ATLAS_PUBLIC_TOMTOM_CONFIRMED = os.environ.get("ATLAS_PUBLIC_TOMTOM_CONFIRMED", "0") == "1"
ATLAS_PROVIDER_TIMEOUT_SECONDS = min(
    25, max(3, int(os.environ.get("ATLAS_PROVIDER_TIMEOUT_SECONDS", "12")))
)
ATLAS_ACQUISITION_SECONDS = min(
    120, max(30, int(os.environ.get("ATLAS_ACQUISITION_SECONDS", "100")))
)
ATLAS_READ_REQUESTS_PER_MINUTE = 300
ATLAS_WRITE_REQUESTS_PER_MINUTE = 12
ATLAS_AUTH_FAILURES_PER_MINUTE = 30
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "atlas.api.errors.exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Spotter Atlas assessment API",
    "DESCRIPTION": "Explicit sample/live sources and authoritative deterministic risk. Hosted live use requires separate permission switches.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "AssessmentReviewer": {
                "type": "http",
                "scheme": "bearer",
                "description": "Private reviewer code required on hosted API paths except health. Local access defaults open.",
            }
        }
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "atlas.api.schema.assessment_security",
    ],
    "ENUM_NAME_OVERRIDES": {
        "RequestMode": ["sample", "live", "actual"],
        "SampleMode": ["sample"],
        "AnalysisMode": ["sample", "live"],
        "RiskLevel": ["low", "moderate", "high", "severe", "no_travel", "unknown"],
        "ScenarioId": ["complete", "partial", "no-travel"],
    },
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "atlas.middleware.SafeJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {
        "atlas": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
