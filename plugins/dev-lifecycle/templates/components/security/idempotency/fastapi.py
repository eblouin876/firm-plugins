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

--- `principal_getter` is REQUIRED, and this middleware MUST run AFTER auth
(judgment call -- see the component README's "Principal scoping" section
for the full rationale) ---
`IdempotencyMiddleware`/`add_idempotency()` take a REQUIRED
`principal_getter: Callable[[Request], str | None]` -- there is no default,
because defaulting to "no principal" would silently reintroduce the exact
cross-principal replay this middleware exists to prevent (see `_core.py`'s
module docstring). `principal_getter` receives the raw `Request` and
returns the caller-identifying string to scope the storage key to (e.g.
`lambda request: request.state.user_id` after an auth middleware has
populated `request.state.user_id`), or `None`/empty for a request this
project does not consider to have an identifiable principal.

Because `principal_getter` reads request state an EARLIER middleware must
have populated, `IdempotencyMiddleware` MUST be added to the app AFTER
(meaning: `app.add_middleware()` called BEFORE, since Starlette runs
middleware in reverse-of-registration order for the request path -- see
Starlette's own docs) any authentication middleware. Add it last (i.e.
call `add_idempotency()`/`add_middleware(IdempotencyMiddleware, ...)`
before any auth middleware registration) so auth actually runs first on
each request.

**Anonymous-request policy (fail closed, documented, not a silent
default):** if `principal_getter(request)` returns `None` or an empty
string, this middleware treats the request EXACTLY as if it had no
`Idempotency-Key` header at all -- full passthrough, no dedup, no replay,
no storage write. This is a deliberate default-deny: an anonymous request
has no stable identity to scope a storage key to, and falling back to a
single shared "anonymous" namespace would reintroduce cross-client replay
for every unauthenticated caller, which is the same class of bug this
whole fix exists to close. A deployer who genuinely needs idempotency
protection on unauthenticated traffic (e.g. an unauthenticated checkout
flow) opts in EXPLICITLY, in their own `principal_getter`, by falling back
to a per-client namespace instead of `None` -- e.g. `lambda request:
request.state.user_id or f"anon-ip:{request.client.host}"` -- never a
single fixed string shared by every anonymous caller.
"""

from __future__ import annotations

import logging
from typing import Callable

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
        principal_getter: Callable[[Request], str | None],
        header_name: str = "Idempotency-Key",
    ) -> None:
        super().__init__(app)
        self.store = store
        self.principal_getter = principal_getter
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_key = request.headers.get(self.header_name)
        if not raw_key:
            return await call_next(request)

        principal = self.principal_getter(request)
        if not principal:
            # Anonymous request under the default fail-closed policy: treat
            # exactly like "no Idempotency-Key header" -- see this module's
            # docstring's "Anonymous-request policy" section.
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
        storage_key = _core.compute_storage_key(principal, key)

        try:
            outcome = _core.check(self.store, storage_key, fingerprint)
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
                storage_key,
                fingerprint,
                _core.StoredResponse(
                    status_code=response.status_code,
                    headers=tuple(response.headers.items()),
                    body=body,
                ),
            )

        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))


def add_idempotency(
    app: Starlette,
    *,
    store: _core.IdempotencyStore,
    principal_getter: Callable[[Request], str | None],
    header_name: str = "Idempotency-Key",
) -> None:
    """Convenience wiring: `add_idempotency(app,
    store=InMemoryIdempotencyStore(), principal_getter=...)` in place of the
    two-line `app.add_middleware(IdempotencyMiddleware, store=...,
    principal_getter=..., header_name=...)` a caller would otherwise write
    by hand. `principal_getter` is required -- see `IdempotencyMiddleware`'s
    module docstring for why there is no default and for the anonymous-
    request policy."""
    app.add_middleware(
        IdempotencyMiddleware, store=store, principal_getter=principal_getter, header_name=header_name
    )
