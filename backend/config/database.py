"""Strict PostgreSQL URL configuration; no secret-bearing configuration logs."""

from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def hosted_mode(environment):
    mode = environment.get("ATLAS_DEPLOYMENT", "local")
    if mode not in {"local", "hosted"}:
        raise ImproperlyConfigured("ATLAS_DEPLOYMENT must be local or hosted.")
    # Render must never acquire local-mode bypasses when a flag is omitted/mistyped.
    return mode == "hosted" or environment.get("RENDER", "").lower() == "true"


def database_config(url, *, hosted=False):
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, strict_parsing=True)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or not parsed.path.strip("/")
            or parsed.fragment
            or any(len(values) != 1 for values in query.values())
            or set(query) - {"sslmode", "sslrootcert", "channel_binding"}
        ):
            raise ValueError
        sslmode = query.get("sslmode", ["verify-full" if hosted else "prefer"])[0]
        if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ValueError
        if hosted and sslmode != "verify-full":
            raise ValueError
        options = {"connect_timeout": 10, "sslmode": sslmode, "prepare_threshold": None}
        if hosted or "sslrootcert" in query:
            options["sslrootcert"] = query.get("sslrootcert", ["system"])[0]
        if "channel_binding" in query:
            options["channel_binding"] = query["channel_binding"][0]
            if options["channel_binding"] not in {"disable", "prefer", "require"}:
                raise ValueError
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": options,
        }
    except (ValueError, TypeError):
        raise ImproperlyConfigured(
            "DATABASE_URL must be PostgreSQL; hosted connections require sslmode=verify-full."
        ) from None
