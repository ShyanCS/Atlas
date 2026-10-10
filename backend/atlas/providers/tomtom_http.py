"""Bounded HTTPS transport for authorized Gate 2 diagnostics; no retries or raw logs."""

import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path


class ProviderError(RuntimeError):
    def __init__(self, code, *, status=None, retry_after=None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        super().__init__(code)  # Never include a credential-bearing URL/provider error body.


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Gate2TomTomBudget:
    """Milestone-wide durable caps. Lock held across send/receive: one in flight.

    Failed/time-out attempts are counted; credentials and response bodies are absent.
    One explicitly authorized extra routing attempt is supported; geocoding stays
    capped at six. No implicit reset. Auth/quota failure latches a stop.
    """

    def __init__(self, path, *, approved_extra_routing_call=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".lock")
        self._thread_lock = threading.Lock()
        self.routing_cap = 7 if approved_extra_routing_call is True else 6

    def read(self):
        if self.path.exists():
            try:
                ledger = json.loads(self.path.read_text())
                for operation in ("routing", "geocoding"):
                    value = ledger[operation]
                    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 7:
                        raise ValueError
                if ledger["geocoding"] > 6:
                    raise ValueError
                return ledger
            except (OSError, ValueError, KeyError, TypeError):
                raise ProviderError("BUDGET_STORAGE_INVALID") from None
        return {
            "routing": 0,
            "geocoding": 0,
            "routing_cap": 6,
            "geocoding_cap": 6,
            "stop_code": None,
        }

    def _save(self, ledger):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(ledger, indent=2) + "\n")
        for attempt in range(20):
            try:
                temp.replace(self.path)
                return
            except PermissionError:
                if attempt == 19:
                    raise ProviderError("BUDGET_STORAGE_UNAVAILABLE") from None
                time.sleep(0.1)  # Filesystem retry only; never repeat an HTTP attempt.

    @contextmanager
    def claim(self, operation):
        if operation not in ("routing", "geocoding"):
            raise ProviderError("INVALID_BUDGET_OPERATION")
        if not self._thread_lock.acquire(blocking=False):
            raise ProviderError("PROVIDER_BUSY")
        lock = None
        locked = False
        try:
            lock = self.lock_path.open("a+b")
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                if __import__("os").name == "nt":
                    import msvcrt

                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                raise ProviderError("PROVIDER_BUSY") from None
            ledger = self.read()
            if ledger.get("stop_code"):
                raise ProviderError(ledger["stop_code"])
            cap = self.routing_cap if operation == "routing" else 6
            if ledger[operation] >= cap:
                raise ProviderError("MILESTONE_REQUEST_CAP")
            ledger["routing_cap"] = self.routing_cap
            ledger[operation] += 1
            self._save(ledger)
            try:
                yield
            except ProviderError as error:
                if error.status in (401, 403, 429):
                    ledger["stop_code"] = error.code
                    self._save(ledger)
                raise
        finally:
            if locked:
                lock.seek(0)
                if __import__("os").name == "nt":
                    import msvcrt

                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock, fcntl.LOCK_UN)
            if lock:
                lock.close()
            self._thread_lock.release()


class TomTomHTTP:
    def __init__(self, api_key, budget, *, timeout_seconds=25, opener=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ProviderError("CREDENTIAL_UNAVAILABLE")
        self._key = api_key.strip()
        self._budget = budget
        self._timeout = timeout_seconds
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def get_json(self, operation, path, parameters):
        if operation == "routing":
            valid = path.startswith("/routing/1/calculateRoute/") and path.endswith("/json")
        else:
            valid = (
                operation == "geocoding"
                and path.startswith("/search/2/geocode/")
                and path.endswith(".json")
            )
        if not valid or any(c in path for c in ("?", "#", "\r", "\n")):
            raise ProviderError("UNAPPROVED_PROVIDER_PATH")
        url = (
            "https://api.tomtom.com"
            + path
            + "?"
            + urllib.parse.urlencode([*parameters, ("key", self._key)])
        )
        with self._budget.claim(operation):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "SpotterAtlas-Gate2-local-diagnostic/1.0",
                    "Accept": "application/json",
                },
            )
            try:
                response = self._opener.open(request, timeout=self._timeout)
            except urllib.error.HTTPError as error:
                status = error.code
                raw_retry = error.headers.get("Retry-After", "")
                retry_after = raw_retry if raw_retry.isdigit() and len(raw_retry) <= 8 else None
                error.close()
                code = {
                    401: "PROVIDER_UNAUTHORIZED",
                    403: "PROVIDER_FORBIDDEN",
                    429: "PROVIDER_QUOTA",
                    400: "PROVIDER_BAD_INPUT",
                }.get(status, "PROVIDER_HTTP_ERROR")
                raise ProviderError(code, status=status, retry_after=retry_after) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                raise ProviderError("PROVIDER_CONNECTION_FAILURE") from None
            with response:
                limit = 6 * 1024**2
                length = response.headers.get("Content-Length")
                if length and (not length.isdigit() or len(length) > 12):
                    raise ProviderError("PROVIDER_INVALID_LENGTH")
                if length and int(length) > limit:
                    raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                try:
                    body = response.read(limit + 1)
                except http.client.IncompleteRead:
                    raise ProviderError("PROVIDER_TRUNCATED_RESPONSE") from None
                except (TimeoutError, OSError):
                    raise ProviderError("PROVIDER_CONNECTION_FAILURE") from None
                if length and len(body) != int(length):
                    raise ProviderError("PROVIDER_TRUNCATED_RESPONSE")
                if len(body) > limit:
                    raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                if response.status != 200:
                    raise ProviderError("PROVIDER_HTTP_ERROR", status=response.status)
            try:
                # Exact JSON numbers and redaction even if a provider echoes the key.
                from decimal import Decimal

                text = body.decode().replace(self._key, "[REDACTED]")

                def reject_constant(value):
                    raise ValueError("Nonfinite JSON")

                return json.loads(text, parse_float=Decimal, parse_constant=reject_constant)
            except (UnicodeDecodeError, ValueError):
                raise ProviderError("PROVIDER_INVALID_JSON") from None
