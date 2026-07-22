"""Framework-neutral idempotency-key handling: Idempotency-Key extraction/
validation (bounded length, safe charset), a fingerprint (method + path +
body-hash) that distinguishes a genuine replay from the same key being
reused for a different request, and pluggable storage (an `IdempotencyStore`
Protocol, with a stdlib in-memory implementation included). Canon:
references/security/payments-security.md ("Idempotency keys" -- pass an
idempotency key on every payment-mutating request ... a retried request
(network blip, client double-submit) must never double-charge).

Drop-in: copy this file into app/core/security/idempotency/_core.py (keep
it alongside fastapi.py/django.py from the same directory). Stdlib only.

A Redis-backed `IdempotencyStore` is Stage 11 work (see the component
README) -- this module deliberately does NOT import `redis`.
`RedisIdempotencyStore` below is a stub only: it pins the shape a real
implementation must satisfy and fails loudly (`NotImplementedError`) if
constructed, rather than silently no-op-ing. The `IdempotencyStore`
Protocol is exactly the seam a real Redis implementation (using `SET key
value NX EX <ttl>` for atomic first-writer-wins reservation across
processes, unlike this module's in-memory store) plugs into without this
file or either framework adapter changing.

Never logs an Idempotency-Key's VALUE -- every exception message and log
line below carries only shapes/counts/exception types, matching the
webhook-signature component's posture for signature/secret values.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Protocol

# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------

# Conservative and deliberately narrower than "anything a client might send":
# this key becomes a storage lookup key (and, in a Redis-backed store, part
# of a cache key) -- unbounded length or pathological characters are exactly
# the kind of input a storage layer should never have to trust blindly.
MAX_KEY_LENGTH = 255
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-.]+$")


class IdempotencyError(Exception):
    """Base class for every error this module raises. A caller (a FastAPI
    middleware, a Django middleware) catches this one type for uniform
    handling, and inspects the subtype only for logging/response-shaping
    -- matching webhook-signature's `WebhookVerificationError` posture."""


class InvalidIdempotencyKeyError(IdempotencyError):
    """Raised when the Idempotency-Key header fails validation: missing/
    empty, longer than MAX_KEY_LENGTH, or containing a character outside
    the safe charset (letters, digits, '-', '_', '.'). Message never
    echoes the raw key value -- only its length or the fact it failed the
    charset check."""


class IdempotencyConflictError(IdempotencyError):
    """Raised when an Idempotency-Key already has a first-seen record
    whose fingerprint (method + path + body-hash) does NOT match this
    request's fingerprint -- the same key reused for a materially
    different request. Callers translate this into a 409 response. Message
    never echoes the key value or either fingerprint."""


def validate_key(raw_key: str | None) -> str:
    """Validates and returns an Idempotency-Key header value. Raises
    `InvalidIdempotencyKeyError` if `raw_key` is `None`/empty, exceeds
    `MAX_KEY_LENGTH`, or contains any character outside the safe charset.
    A caller passes the raw header value straight through -- this function
    is the only place that charset/length rule lives, so both framework
    adapters enforce it identically."""
    if not raw_key:
        raise InvalidIdempotencyKeyError("Idempotency-Key header is missing or empty")
    if len(raw_key) > MAX_KEY_LENGTH:
        raise InvalidIdempotencyKeyError(
            f"Idempotency-Key exceeds the {MAX_KEY_LENGTH}-character limit"
        )
    if not _KEY_PATTERN.match(raw_key):
        raise InvalidIdempotencyKeyError(
            "Idempotency-Key contains a character outside the allowed set "
            "(letters, digits, '-', '_', '.')"
        )
    return raw_key


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def compute_fingerprint(method: str, path: str, raw_body: bytes) -> str:
    """The fact this Idempotency-Key was actually used for: HTTP method
    (uppercased), request path (no query string -- the key is meant to
    dedupe a specific mutating operation, not vary by query params), and a
    SHA-256 hash of the RAW request body (never a parsed/re-serialized
    body -- same rationale as webhook-signature's raw-body requirement:
    key ordering/whitespace/unicode differences in a re-serialized body
    would produce a different hash for byte-identical intent). Two
    requests with the same key and the same fingerprint are a genuine
    retry; the same key with a different fingerprint is a reused key on a
    materially different request -- see `check()`."""
    body_hash = hashlib.sha256(raw_body).hexdigest()
    return f"{method.upper()}:{path}:{body_hash}"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredResponse:
    """The response captured for a first-seen request, replayed verbatim
    on a later request with the same key + fingerprint."""

    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """What a store persists per key: the fingerprint the key was first
    used with (to detect a conflicting reuse) and the response to replay.
    `created_at` is captured for a future TTL/eviction policy (e.g. a
    Redis store's `EX` on the Stage 11 backend) -- this module's in-memory
    store does not itself expire records; see `InMemoryIdempotencyStore`'s
    docstring."""

    fingerprint: str
    response: StoredResponse
    created_at: float


class IdempotencyStore(Protocol):
    """The storage seam idempotency records live behind. `get()`/`put()`
    are the only two operations a framework adapter needs; the adapter
    itself owns the "is this a replay or a conflict" decision via
    `check()` below, so a store implementation stays a plain key-value
    store and never has to know about fingerprints or the conflict rule
    itself."""

    def get(self, key: str) -> IdempotencyRecord | None: ...

    def put(self, key: str, record: IdempotencyRecord) -> None: ...


class InMemoryIdempotencyStore:
    """Stdlib-only in-memory idempotency store, one dict entry per key,
    guarded by a lock for the same atomicity posture as rate-limiting's
    `InMemoryBucketStore`.

    Known limitations, documented rather than hidden (same posture as
    `InMemoryBucketStore`'s per-process note):

    - **Per-process.** A multi-worker deployment (gunicorn with N workers,
      multiple ECS tasks) gives each worker its own independent view of
      which keys have been seen -- two concurrent requests with the same
      Idempotency-Key landing on DIFFERENT workers are not deduplicated
      against each other, only against requests the same worker has
      already completed. A single-process dev server or single-replica
      deployment is fully protected; a multi-worker/multi-replica
      deployment needs the Redis-backed `IdempotencyStore` (Stage 11) for
      a true shared, atomic guarantee -- see the component README's
      "Judgment calls".
    - **No reservation across the request lifecycle.** A record is only
      written AFTER the downstream handler completes (see each framework
      adapter's `dispatch`/`__call__`), so two truly concurrent requests
      with the same key hitting the SAME process at the same instant can
      both observe "no record yet" and both execute the underlying side
      effect once each, before either response is recorded. Closing that
      race requires an atomic reserve-then-execute-then-complete state
      machine, which a Redis store's `SET NX` gives naturally -- this
      store optimizes for the common case payments-security.md targets
      (a retried request after a timeout/network blip), not true
      concurrent double-submission.
    - **No expiry.** Records live for the lifetime of the process; a
      Redis-backed store would set a TTL (`EX`) so old keys are reclaimed
      automatically. `IdempotencyRecord.created_at` is captured so a
      future eviction policy has what it needs, but this store does not
      act on it.
    """

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get(key)

    def put(self, key: str, record: IdempotencyRecord) -> None:
        with self._lock:
            self._records[key] = record


class RedisIdempotencyStore:
    """Stub for the Stage 11 Redis-backed `IdempotencyStore` -- NOT
    implemented here, and this module never imports `redis`. Exists only
    to pin the shape a real implementation must satisfy (the same
    `IdempotencyStore` Protocol `InMemoryIdempotencyStore` implements) and
    to fail loudly and clearly if something tries to construct or use it
    before Stage 11 builds it out, rather than silently no-op-ing or
    behaving like an in-memory store under a misleading name.

    A real implementation would use `SET key value NX EX <ttl>` for
    atomic first-writer-wins reservation (the piece
    `InMemoryIdempotencyStore`'s "no reservation across the request
    lifecycle" limitation can't provide across processes), storing a
    serialized `IdempotencyRecord` as the value and letting Redis' own
    `EX` handle expiry instead of the manual eviction an in-memory store
    would need."""

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "RedisIdempotencyStore is a Stage 11 stub -- construct an "
            "InMemoryIdempotencyStore for now, or implement this class "
            "against your Redis client of choice using SET NX EX for "
            "atomic first-writer-wins reservation."
        )

    def get(self, key: str) -> IdempotencyRecord | None:
        raise NotImplementedError

    def put(self, key: str, record: IdempotencyRecord) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# The check/record cycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdempotencyOutcome:
    """The result of `check()`. `is_replay=False` means this key/
    fingerprint pair has never been seen -- the caller should proceed with
    the request and call `record_response()` once it has a response.
    `is_replay=True` means `stored_response` is the exact response to
    return, unchanged, without re-running the handler."""

    is_replay: bool
    stored_response: StoredResponse | None


def check(store: IdempotencyStore, key: str, fingerprint: str) -> IdempotencyOutcome:
    """Looks up `key` in `store`. No record: returns a "proceed" outcome.
    A record whose fingerprint matches: returns a "replay" outcome
    carrying the stored response. A record whose fingerprint does NOT
    match: raises `IdempotencyConflictError` -- the same key was reused
    for a request this component considers materially different (method,
    path, or body all factor into the fingerprint)."""
    existing = store.get(key)
    if existing is None:
        return IdempotencyOutcome(is_replay=False, stored_response=None)
    if existing.fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "Idempotency-Key was already used for a different request "
            "(different method, path, or body)"
        )
    return IdempotencyOutcome(is_replay=True, stored_response=existing.response)


def record_response(
    store: IdempotencyStore,
    key: str,
    fingerprint: str,
    response: StoredResponse,
    *,
    now: float | None = None,
) -> None:
    """Persists `response` as the first-seen record for `key` +
    `fingerprint`. `now` defaults to `time.time()` (wall-clock -- unlike
    rate-limiting's `time.monotonic()`, this timestamp is metadata for a
    future TTL policy, not itself driving any in-process math, so a
    wall-clock value is the more useful one to have persisted). Both
    framework adapters call this only after a downstream handler has
    produced a response with a non-5xx status -- see each adapter's
    module docstring for that judgment call."""
    resolved_now = now if now is not None else time.time()
    store.put(key, IdempotencyRecord(fingerprint=fingerprint, response=response, created_at=resolved_now))
