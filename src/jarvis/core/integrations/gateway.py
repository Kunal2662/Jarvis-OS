"""API Gateway -- Milestone 11 Task Group E.

The single audited egress point every outbound integration call passes
through: one ``httpx`` client pool, one retry policy, one response
cache, one place rate limits are understood, and one place a call is
recorded. The roadmap's "API Gateway -- a single, audited egress point
for outbound integration traffic" is this class.

**Why one gateway rather than a client per connector.** Thirty
connectors each holding their own ``httpx.AsyncClient`` would mean
thirty connection pools, thirty retry bugs to find, and no single place
to answer "what did JARVIS call, and what happened". The connectors are
data (``models.py``); this executes them.

**Retry is refused for mutating calls, on purpose.** A retried ``GET``
costs a round trip. A retried ``POST /messages/send`` sends the email
twice, and no amount of backoff makes that acceptable -- the vendor
APIs here are not idempotent and do not all accept an idempotency key.
So :class:`ApiGateway` retries idempotent methods only, and a mutating
call that fails fails once, visibly. Overriding that is deliberately not
a parameter.

**The cache is read-only and short.** Only successful ``GET`` responses
are cached, keyed by the full resolved request *including the account*,
so one user's inbox listing can never be served to another. Any
mutating call to the same integration drops that integration's cached
entries, because a caller who just sent a message and then lists
messages must not be told the message is not there.

**Secrets never reach a log line.** The gateway is handed a header
value it never inspects, records request *metadata* only, and its
:class:`GatewayResult` carries no ``Authorization`` header. The audit
trail says which operation ran against which integration with what
outcome -- never with what token.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis.core.integrations.models import IntegrationError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = get_logger("jarvis.core.integrations.gateway")

#: Methods safe to replay. Deliberately excludes every mutating method
#: -- see the module docstring.
RETRYABLE_METHODS: frozenset[str] = frozenset({"GET"})

#: Status codes worth a second attempt: a rate limit and the four
#: server-side failures that are routinely transient. A 4xx other than
#: 429 is the caller's fault and retrying it just spends quota.
RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5
DEFAULT_CACHE_TTL_SECONDS = 30.0
DEFAULT_CACHE_ENTRIES = 256

#: How long to wait when a vendor sends ``Retry-After`` but the value is
#: unusable or absurd. Honouring an hour-long hint inside a request
#: would hang the caller; ignoring the header entirely would hammer a
#: service that just asked us to stop.
MAX_HONOURED_RETRY_AFTER_SECONDS = 60.0


class GatewayError(IntegrationError):
    """An outbound call that could not be completed.

    Carries the HTTP status when there was one, so a caller can tell a
    vendor's ``403 insufficient scope`` from a DNS failure without
    parsing a message string. ``kind`` distinguishes a *timeout*
    (``httpx.TimeoutException``) from any other transport failure (DNS,
    connection refused, TLS, ...) when no status code was ever received
    -- M11 Task Group B's Connection Testing needs this to classify a
    slow vendor differently from an unreachable one.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        kind: str = "http",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.kind = kind


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """One resolved outbound call. Built by the provider from a spec and
    a caller's parameters; the gateway never constructs a URL itself."""

    integration_id: str
    operation: str
    method: str
    url: str
    query: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    #: Distinguishes one authenticated account's cache entries from
    #: another's. Empty is a real value (an unauthenticated endpoint),
    #: not a wildcard.
    account_key: str = ""
    cacheable: bool = True
    #: Overrides the gateway's configured timeout for this call only.
    #: ``None`` means "use the gateway's own timeout" -- every existing
    #: caller leaves this unset. M11 Task Group B's Connection Testing
    #: sets a shorter, caller-facing bound here, enforced by ``httpx``
    #: at the actual socket, not by wrapping the call in a higher-level
    #: ``asyncio.wait_for``.
    timeout_seconds: float | None = None
    #: One attempt, no retry, even for an otherwise-retryable GET.
    #: Mirrors the existing "mutating calls never retry" rule for a
    #: different reason: a Connection Test is a diagnostic, and retrying
    #: it would turn "is this broken right now" into "keep trying until
    #: it isn't" -- see ``_attempts_for``.
    single_attempt: bool = False

    @property
    def mutating(self) -> bool:
        return self.method not in RETRYABLE_METHODS

    def cache_key(self) -> str:
        items = "&".join(f"{k}={self.query[k]}" for k in sorted(self.query))
        return f"{self.account_key}|{self.method} {self.url}?{items}"

    def audit(self) -> dict[str, Any]:
        """Metadata for the log and the event. Never headers, never a
        body -- a request body can carry the text of an email."""
        return {
            "integration_id": self.integration_id,
            "operation": self.operation,
            "method": self.method,
            "url": self.url,
            "query_keys": sorted(self.query),
            "has_body": self.body is not None,
        }


@dataclass(frozen=True, slots=True)
class GatewayResult:
    """What came back."""

    request: GatewayRequest
    status_code: int
    data: Any = None
    attempts: int = 1
    from_cache: bool = False
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.request.audit(),
            "status_code": self.status_code,
            "attempts": self.attempts,
            "from_cache": self.from_cache,
            "duration_ms": round(self.duration_ms, 2),
        }


class _ResponseCache:
    """A tiny bounded TTL cache. Not a caching subsystem -- there is no
    persistence, no invalidation protocol and no sharing between
    processes, because a 30-second in-memory window is all this needs to
    stop a UI polling three panels from making the same call three
    times."""

    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: dict[str, tuple[float, int, Any]] = {}

    def get(self, key: str) -> tuple[int, Any] | None:
        found = self._entries.get(key)
        if found is None:
            return None
        stored_at, status, data = found
        if time.monotonic() - stored_at > self._ttl:
            self._entries.pop(key, None)
            return None
        return status, data

    def put(self, key: str, status: int, data: Any) -> None:
        if self._ttl <= 0:
            return
        if len(self._entries) >= self._max:
            # Oldest first. A strict LRU would need access tracking for
            # a cache this small to gain nothing measurable.
            oldest = min(self._entries, key=lambda k: self._entries[k][0])
            self._entries.pop(oldest, None)
        self._entries[key] = (time.monotonic(), status, data)

    def drop_prefix(self, prefix: str) -> int:
        doomed = [k for k in self._entries if k.startswith(prefix)]
        for key in doomed:
            self._entries.pop(key, None)
        return len(doomed)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


class ApiGateway:
    """The one place outbound integration traffic leaves JARVIS."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_entries: int = DEFAULT_CACHE_ENTRIES,
        verify: bool = True,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff = max(0.0, backoff_seconds)
        self._verify = verify
        self._cache = _ResponseCache(ttl_seconds=cache_ttl_seconds, max_entries=cache_entries)
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._calls = 0
        self._failures = 0
        self._cache_hits = 0
        self._retries = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Open the shared pool. Idempotent, and guarded -- two
        providers connecting concurrently must not each build a client
        and leave one of them unclosed."""
        async with self._lock:
            if self._client is not None:
                return
            import httpx

            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                verify=self._verify,
                headers={"Accept": "application/json"},
            )
            _logger.info("API gateway opened (timeout={}s).", self._timeout)

    async def stop(self) -> None:
        async with self._lock:
            client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()
            except Exception as err:  # pragma: no cover -- defensive
                _logger.debug("API gateway close failed: {}", err)
        self._cache.clear()

    @property
    def is_open(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Egress
    # ------------------------------------------------------------------
    async def send(self, request: GatewayRequest) -> GatewayResult:
        """Perform one outbound call, with cache, retry and audit.

        Raises :class:`GatewayError` on a non-2xx response or a
        transport failure. Returning a failed result instead would make
        every caller check ``ok`` and most of them forget.
        """
        if self._client is None:
            raise GatewayError(f"Cannot call {request.operation!r}: the API gateway is not open.")

        cached = self._lookup_cache(request)
        if cached is not None:
            return cached

        started = time.monotonic()
        last_error: str = ""
        last_kind: str = "network"
        status_code: int | None = None

        for attempt in range(1, self._attempts_for(request) + 1):
            try:
                status_code, data, retry_after = await self._attempt(request)
            except Exception as err:  # transport-level: DNS, TLS, timeout
                last_error = str(err)
                last_kind = "timeout" if _is_timeout(err) else "network"
                if attempt >= self._attempts_for(request):
                    break
                self._retries += 1
                await asyncio.sleep(self._backoff * attempt)
                continue

            if 200 <= status_code < 300:
                duration = (time.monotonic() - started) * 1000
                self._calls += 1
                return self._finish(request, status_code, data, attempt, duration)

            last_error = _describe(status_code, data)
            if status_code not in RETRYABLE_STATUSES or attempt >= self._attempts_for(request):
                break
            self._retries += 1
            await asyncio.sleep(retry_after if retry_after is not None else self._backoff * attempt)

        self._calls += 1
        self._failures += 1
        _logger.warning(
            "Integration call failed: {} {} -> {}",
            request.integration_id,
            request.operation,
            last_error,
        )
        raise GatewayError(
            f"{request.integration_id}.{request.operation} failed: {last_error}",
            status_code=status_code,
            retryable=status_code in RETRYABLE_STATUSES if status_code else True,
            kind=last_kind if status_code is None else "http",
        )

    # ------------------------------------------------------------------
    # Cache control
    # ------------------------------------------------------------------
    def invalidate(self, account_key: str = "") -> int:
        """Drop cached responses for one account (or everything).

        Called after a mutating operation: a caller who just sent a
        message and then lists messages must not be told it is not
        there. Keyed by account rather than integration because the
        cache key leads with the account -- and because a mutation in
        one account cannot stale another's.
        """
        return self._cache.drop_prefix(account_key) if account_key else self._clear_cache()

    def stats(self) -> dict[str, Any]:
        """Counters for diagnostics. Collected, never computed
        elsewhere -- this is the only object that knows how many
        outbound calls were made."""
        return {
            "open": self.is_open,
            "calls": self._calls,
            "failures": self._failures,
            "retries": self._retries,
            "cache_hits": self._cache_hits,
            "cache_entries": len(self._cache),
            "max_attempts": self._max_attempts,
            "timeout_seconds": self._timeout,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _attempts_for(self, request: GatewayRequest) -> int:
        """One attempt for anything that changes remote state, or that
        must not be silently retried (``single_attempt`` -- M11 Task
        Group B's Connection Testing: a retry would turn a diagnostic
        into "try until it works")."""
        return 1 if request.mutating or request.single_attempt else self._max_attempts

    def _lookup_cache(self, request: GatewayRequest) -> GatewayResult | None:
        if request.mutating or not request.cacheable:
            return None
        found = self._cache.get(request.cache_key())
        if found is None:
            return None
        self._cache_hits += 1
        status, data = found
        return GatewayResult(
            request=request, status_code=status, data=data, from_cache=True, attempts=0
        )

    def _clear_cache(self) -> int:
        size = len(self._cache)
        self._cache.clear()
        return size

    def _finish(
        self, request: GatewayRequest, status: int, data: Any, attempts: int, duration: float
    ) -> GatewayResult:
        if request.mutating:
            # The mutation may have invalidated anything this account
            # previously read; dropping its entries is cheaper than
            # reasoning about which.
            self._cache.drop_prefix(request.account_key)
        elif request.cacheable:
            self._cache.put(request.cache_key(), status, data)
        return GatewayResult(
            request=request,
            status_code=status,
            data=data,
            attempts=attempts,
            duration_ms=duration,
        )

    async def _attempt(self, request: GatewayRequest) -> tuple[int, Any, float | None]:
        """One HTTP round trip. Returns ``(status, parsed, retry_after)``.

        ``timeout_seconds``, when set, overrides the client's default
        for this one request -- ``httpx`` enforces it at the actual
        socket read/connect/write boundary, not as a wrapper around
        this coroutine.
        """
        kwargs: dict[str, Any] = {}
        if request.timeout_seconds is not None:
            kwargs["timeout"] = request.timeout_seconds
        response = await self._client.request(
            request.method,
            request.url,
            params=request.query or None,
            json=request.body if request.body is not None else None,
            headers=request.headers or None,
            **kwargs,
        )
        return response.status_code, _parse(response), _retry_after(response.headers)


def _is_timeout(err: Exception) -> bool:
    import httpx

    return isinstance(err, httpx.TimeoutException)


def _parse(response: Any) -> Any:
    """JSON when the vendor sent JSON, text otherwise.

    Vendors return non-JSON in two ordinary cases -- a downloaded file
    body and an empty ``204`` -- and treating either as a parse failure
    would turn a successful call into an error.
    """
    if not response.content:
        return None
    content_type = str(response.headers.get("content-type", ""))
    if "json" in content_type:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
    if content_type.startswith("text/"):
        return response.text
    return {"content_type": content_type, "bytes": len(response.content)}


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """Honour ``Retry-After`` when it is a sane number of seconds.

    Bounded: a vendor asking us to wait an hour inside a request would
    hang the caller, so the hint is clamped and the shorter wait is
    used. Ignoring it entirely would hammer a service that has just
    asked us to stop.
    """
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, MAX_HONOURED_RETRY_AFTER_SECONDS)


def _describe(status: int, data: Any) -> str:
    """A short, safe rendering of a vendor error.

    Vendors put useful text in ``error.message``; taking it makes a
    failure actionable. It is truncated because some return a full HTML
    error page, and a log line should not become one.
    """
    detail = ""
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("status") or "")
        elif error:
            detail = str(error)
        elif data.get("message"):
            detail = str(data["message"])
    elif isinstance(data, str):
        detail = data
    return f"HTTP {status}{f': {detail[:200]}' if detail else ''}"
