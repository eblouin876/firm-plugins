"""Django wiring for the idempotency component: a MIDDLEWARE class that is a
no-op for any request without an `Idempotency-Key` header, and otherwise
dedupes via `_core.check()`/`_core.record_response()`. Canon:
references/security/payments-security.md ("Idempotency keys").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/idempotency/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`.

Django only (`django`) -- no third-party dependency, no `redis` import.

Configuration reads Django settings (the Django convention), with an
explicit-kwarg override path for direct instantiation (used by this
component's own tests, and available to a project that wants to construct
this middleware itself rather than configure it via settings), matching
rate-limiting/django.py's pattern: `IDEMPOTENCY_HEADER_NAME` (default
`"HTTP_IDEMPOTENCY_KEY"`, the Django `META` form of `Idempotency-Key` --
see this module's own docstring below for that mapping).
"""

from __future__ import annotations

import logging
from typing import Callable

import _core
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

logger = logging.getLogger(__name__)

# Same non-cacheable-server-error rule as fastapi.py -- see that file's
# module docstring for the rationale.
_MAX_CACHEABLE_STATUS = 499

_default_store: _core.IdempotencyStore | None = None


def _get_default_store() -> _core.IdempotencyStore:
    """A module-level singleton store, created lazily on first use and
    shared by every request this process handles -- see _core.py's
    `InMemoryIdempotencyStore` docstring for the per-process limitation
    this implies, matching rate-limiting/django.py's identical pattern."""
    global _default_store
    if _default_store is None:
        _default_store = _core.InMemoryIdempotencyStore()
    return _default_store


class IdempotencyMiddleware:
    """New-style Django middleware. `header_name` is the `request.META`
    key, not the HTTP header name -- Django maps `Idempotency-Key` to
    `HTTP_IDEMPOTENCY_KEY` (uppercase, hyphens to underscores, `HTTP_`
    prefix); pass the `META` form directly, matching
    webhook-signature/django.py's `header_name` convention rather than
    this middleware guessing the mapping."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
        *,
        store: _core.IdempotencyStore | None = None,
        header_name: str | None = None,
    ) -> None:
        self.get_response = get_response
        self.store = store if store is not None else _get_default_store()
        self.header_name = (
            header_name
            if header_name is not None
            else getattr(settings, "IDEMPOTENCY_HEADER_NAME", "HTTP_IDEMPOTENCY_KEY")
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raw_key = request.META.get(self.header_name)
        if not raw_key:
            return self.get_response(request)

        try:
            key = _core.validate_key(raw_key)
        except _core.InvalidIdempotencyKeyError as exc:
            logger.warning("idempotency key rejected: %s", type(exc).__name__)
            return JsonResponse({"detail": "invalid Idempotency-Key"}, status=400)

        raw_body = request.body
        fingerprint = _core.compute_fingerprint(request.method, request.path, raw_body)

        try:
            outcome = _core.check(self.store, key, fingerprint)
        except _core.IdempotencyConflictError as exc:
            logger.warning("idempotency conflict: %s", type(exc).__name__)
            return JsonResponse(
                {"detail": "Idempotency-Key was already used for a different request"},
                status=409,
            )

        if outcome.is_replay:
            stored = outcome.stored_response
            assert stored is not None
            response = HttpResponse(stored.body, status=stored.status_code)
            for name, value in stored.headers:
                response[name] = value
            return response

        response = self.get_response(request)

        if response.status_code <= _MAX_CACHEABLE_STATUS:
            _core.record_response(
                self.store,
                key,
                fingerprint,
                _core.StoredResponse(
                    status_code=response.status_code,
                    headers=tuple(response.items()),
                    body=response.content,
                ),
            )

        return response
