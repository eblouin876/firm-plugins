"""FastAPI/Starlette wiring for the idempotency component: whole-app
middleware that is a no-op for any request without an `Idempotency-Key`
header, and otherwise dedupes via `_core.check()`/`_core.record_response()`.
Canon: references/security/payments-security.md ("Idempotency keys").

Drop-in: copy this whole directory (this file, `_core.py`, `django.py`)
into app/core/security/idempotency/ and keep them together. This file
imports its core logic with a bare `import _core` -- see the
security-headers component's `fastapi.py` for the full rationale.

Starlette/FastAPI only (`starlette`, `fastapi`) -- no third-party
dependency, no `redis` import (see `_core.py`'s module docstring).

Deliberately uses `BaseHTTPMiddleware`, unlike security-headers'/
rate-limiting's pure-ASGI middleware. Those avoid `BaseHTTPMiddleware`
specifically to skip buffering a response body just to add a header or a
429 short-circuit. This component's entire point is buffering and storing
a COMPLETE response body for later verbatim replay -- the buffering
`BaseHTTPMiddleware` performs is exactly the work needed here, not
overhead to avoid. See the component README's "Judgment calls".
"""

from __future__ import annotations

import logging

import _core
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# A downstream handler that fails with a server error is presumed
# transient (a timeout, a dependency outage) rather than a deterministic
# outcome of this exact request -- caching it would permanently deny a
# legitimate retry the chance to actually succeed. 2xx-4xx are
# deterministic outcomes of the request itself and are cached; 5xx is not.
# See the component README's "Judgment calls".
_MAX_CACHEABLE_STATUS = 499


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Whole-app middleware, but opt-in PER REQUEST via the
    `Idempotency-Key` header -- unlike security-headers/CORS/rate-limiting's
    always-on posture, idempotency protection only applies to requests the
    caller marks as retry-sensitive (matching payments-security.md: pass a
    key on every payment-mutating request; a request the caller doesn't
    consider retry-sensitive sends no key and passes through untouched)."""

    def __init__(
        self,
        app,
        *,
        store: _core.IdempotencyStore,
        header_name: str = "Idempotency-Key",
    ) -> None:
        super().__init__(app)
        self.store = store
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_key = request.headers.get(self.header_name)
        if not raw_key:
            return await call_next(request)

        try:
            key = _core.validate_key(raw_key)
        except _core.InvalidIdempotencyKeyError as exc:
            logger.warning("idempotency key rejected: %s", type(exc).__name__)
            return JSONResponse({"detail": "invalid Idempotency-Key"}, status_code=400)

        # Starlette caches the raw body internally on first `.body()` read,
        # so the downstream handler (reached via call_next) sees the same
        # cached bytes rather than a second read of an already-consumed
        # stream -- same guarantee webhook-signature's fastapi.py relies on.
        raw_body = await request.body()
        fingerprint = _core.compute_fingerprint(request.method, request.url.path, raw_body)

        try:
            outcome = _core.check(self.store, key, fingerprint)
        except _core.IdempotencyConflictError as exc:
            logger.warning("idempotency conflict: %s", type(exc).__name__)
            return JSONResponse(
                {"detail": "Idempotency-Key was already used for a different request"},
                status_code=409,
            )

        if outcome.is_replay:
            stored = outcome.stored_response
            assert stored is not None
            return Response(
                content=stored.body,
                status_code=stored.status_code,
                headers=dict(stored.headers),
            )

        response = await call_next(request)
        body = b"".join([chunk async for chunk in response.body_iterator])

        if response.status_code <= _MAX_CACHEABLE_STATUS:
            _core.record_response(
                self.store,
                key,
                fingerprint,
                _core.StoredResponse(
                    status_code=response.status_code,
                    headers=tuple(response.headers.items()),
                    body=body,
                ),
            )

        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))


def add_idempotency(
    app: Starlette, *, store: _core.IdempotencyStore, header_name: str = "Idempotency-Key"
) -> None:
    """Convenience wiring: `add_idempotency(app, store=InMemoryIdempotencyStore())`
    in place of the two-line `app.add_middleware(IdempotencyMiddleware,
    store=..., header_name=...)` a caller would otherwise write by hand."""
    app.add_middleware(IdempotencyMiddleware, store=store, header_name=header_name)
