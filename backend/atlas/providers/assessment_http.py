"""Finite local assessment request allowance; no retries, redirects or paid fallback."""

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from atlas.providers.tomtom_http import NoRedirect, ProviderError


class AssessmentBudget:
    """One process/file lease across HTTP; attempts debit before I/O, never auto-reset."""

    def __init__(self, path, caps=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.caps = caps or {"routing": 8, "geocoding": 12, "weather": 64}
        self.lock = threading.Lock()

    @contextmanager
    def claim(self, operation):
        if operation not in self.caps:
            raise ProviderError("INVALID_BUDGET_OPERATION")
        if not self.lock.acquire(blocking=False):
            raise ProviderError("PROVIDER_BUSY")
        handle, locked = None, False
        try:
            handle = self.path.with_suffix(".lock").open("a+b")
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                raise ProviderError("PROVIDER_BUSY") from None
            try:
                ledger = (
                    json.loads(self.path.read_text())
                    if self.path.exists()
                    else {"counts": dict.fromkeys(self.caps, 0), "stop_code": None}
                )
                if any(
                    type(ledger["counts"][k]) is not int or ledger["counts"][k] < 0
                    for k in self.caps
                ):
                    raise ValueError
            except (ValueError, KeyError, OSError, TypeError):
                raise ProviderError("BUDGET_STORAGE_INVALID") from None
            if ledger["stop_code"]:
                raise ProviderError(ledger["stop_code"])
            if ledger["counts"][operation] >= self.caps[operation]:
                raise ProviderError("ASSESSMENT_REQUEST_CAP")
            ledger["counts"][operation] += 1
            self.path.write_text(json.dumps(ledger))
            try:
                yield
            except ProviderError as error:
                if error.status in (401, 403, 429):
                    ledger["stop_code"] = error.code
                    self.path.write_text(json.dumps(ledger))
                raise
        finally:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_UN)
            if handle:
                handle.close()
            self.lock.release()


def https_opener(ca_bundle=None):
    context = ssl.create_default_context(cafile=ca_bundle or None)
    return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))


class OpenMeteoHTTP:
    def __init__(self, budget, *, opener=None, timeout_seconds=12):
        self.budget = budget
        self.opener = opener or https_opener(os.environ.get("ATLAS_CA_BUNDLE"))
        self.timeout_seconds = timeout_seconds

    def get_json(self, parameters):
        # Fixed origin; no caller-supplied URLs, keys or redirects.
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(parameters)
        with self.budget.claim("weather"):
            try:
                with self.opener.open(
                    urllib.request.Request(
                        url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "SpotterAtlas-assessment/1.0",
                        },
                    ),
                    timeout=self.timeout_seconds,
                ) as response:
                    body = response.read(2 * 1024**2 + 1)
                    if len(body) > 2 * 1024**2:
                        raise ProviderError("WEATHER_RESPONSE_TOO_LARGE")
                    if response.status != 200:
                        raise ProviderError("WEATHER_HTTP_ERROR", status=response.status)
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                raise ProviderError(
                    "WEATHER_QUOTA" if status == 429 else "WEATHER_HTTP_ERROR", status=status
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                raise ProviderError("WEATHER_CONNECTION_FAILURE") from None
            try:

                def invalid_constant(value):
                    raise ValueError("Nonfinite JSON")

                payload = json.loads(body, parse_float=Decimal, parse_constant=invalid_constant)
                if isinstance(payload, dict) and payload.get("error"):
                    raise ValueError
                return payload
            except (ValueError, UnicodeDecodeError):
                raise ProviderError("WEATHER_INVALID_JSON") from None


class DeadlineBudget:
    """Bound acquisition between requests; socket timeouts remain per I/O."""

    def __init__(self, budget, seconds):
        self.budget = budget
        self.deadline = time.monotonic() + seconds

    @contextmanager
    def claim(self, operation):
        if time.monotonic() >= self.deadline:
            raise ProviderError("PROVIDER_ACQUISITION_TIMEOUT")
        with self.budget.claim(operation):
            yield
        if time.monotonic() >= self.deadline:
            raise ProviderError("PROVIDER_ACQUISITION_TIMEOUT")
