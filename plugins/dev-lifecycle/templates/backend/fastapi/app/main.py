"""`create_app()` factory: registers routers, registers the two exception
handlers the `error-envelope` contract requires (RequestValidationError ->
ErrorEnvelope 422; AppError hierarchy -> ErrorEnvelope with each
subclass's own status/code), configures OpenAPI metadata + the bearer
security scheme for the Stage 5 auth seam, and wires the Stage 3 Step 3b
(#26) security-composition middleware stack — see "Security composition"
below for the full, load-bearing order.

--- Security composition (Stage 3 #26, Step 3b) ------------------------
Four of the six vendored `app/core/security/` components are wired here as
middleware; the other two (secret_store, input_validation) are library
code composed at the point of use, not middleware (see app/core/config.py's
`jwt_signing_key` for secret_store's composition; app/schemas/item.py's
docstring for why input_validation's StrictModel isn't adopted there).
`webhook_signature` and `idempotency` (also in the component catalog) are
NOT vendored here at all -- they're payments-shaped concerns with no
consumer yet; the Stage 11 payments recipe vendors and wires them when
there's an actual webhook endpoint to protect.

**Middleware order is OUTERMOST -> INNERMOST, top-to-bottom in the prose
below -- but Starlette's `app.add_middleware()` PREPENDS to its internal
list and then builds the runtime stack by iterating that list in REVERSE
(confirmed against this project's pinned Starlette:
`Starlette.add_middleware` calls `self.user_middleware.insert(0, ...)`,
and `Starlette.build_middleware_stack` does
`for cls, args, kwargs in reversed(middleware): app = cls(app, ...)`).
The practical consequence: the LAST `add_middleware()`/`add_cors()`/
`add_security_headers()` call in `create_app()` below ends up OUTERMOST at
runtime. The calls in this factory are therefore ordered bottom-to-top
relative to the prose here -- read the code comments at each call site for
the "call N of 4" position.**

1. **security-headers (OUTERMOST).** Runs first on the way in and, more
   importantly, LAST on the way out -- it gets to set/overwrite headers on
   every response this app ever produces, including a lower layer's own
   response (rate-limiting's 429, CORS's preflight reply, a routed
   handler's normal response). Nothing downstream can suppress these
   headers by constructing its own response object, because this layer
   runs after all of them on the response path.
2. **request-id / audit binding.** Binds a per-request id (inbound
   `X-Request-ID` if shape-valid, else a fresh `uuid4` --
   audit_logging/middleware.py) into audit.py's contextvar BEFORE
   rate-limiting runs, so a rate-limit denial's own audit trail (today:
   none: `rate_limiting.fastapi.RateLimitMiddleware` doesn't call
   `audit_event()` itself -- a future stage that adds one gets the id
   automatically) and every other downstream `audit_event()` call in this
   request already carries it, without threading it through every call
   site by hand -- exactly the seam audit_logging/README.md's "Request-id
   binding (for Step 3 middleware)" section documents.
3. **rate-limiting.** Pre-auth (this app has no real authentication yet --
   Stage 5, #28 -- so "pre-auth" and "for every request" are the same
   thing today), general per-client-IP ceiling. Runs INSIDE request-id
   binding (so a 429 still carries the request id) and OUTSIDE CORS (so an
   attacker can't burn through the rate-limit budget with cross-origin
   preflight `OPTIONS` requests that never even reach CORS's own allow/deny
   decision -- rate limiting sees and counts every request regardless of
   origin).
4. **CORS (INNERMOST of the four).** Closest to routing/exception
   handling. Deny-by-default: wired only when `cors_allowed_origins` is
   non-empty -- see the call site's own comment for why an empty list means
   "skip CORS entirely" rather than constructing a policy that would fail.
------------------------------------------------------------------------
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routers import auth, health, items
from app.core.config import Settings, get_settings
from app.core.db import configure_engine
from app.core.errors import AppError, ErrorBody, ErrorCode, ErrorDetail, ErrorEnvelope
from app.core.security.audit_logging import RequestIDMiddleware
from app.core.security.cors_lockdown import CORSPolicy, add_cors
from app.core.security.rate_limiting import InMemoryBucketStore, RateLimitMiddleware
from app.core.security.security_headers import SecurityHeadersPolicy, add_security_headers

APP_TITLE = "FastAPI block"
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configures the vendored async engine (app/core/db/session.py) from
    this project's settings at startup — the one required call per
    db-session/README.md's "One engine, configured once at startup".
    Deliberately reads `get_settings()` here, not at module import time, so
    a missing/invalid DATABASE_URL fails when the app actually starts
    serving traffic, not at import time in a context (a test collecting
    this module, a one-off script) that never intends to run the app."""
    settings = get_settings()
    configure_engine(settings.database_url)
    yield
    # --- TODO (out of Step 3b's scope) ------------------------------------
    # Graceful engine disposal (`await get_engine().dispose()`) still lands
    # here in a later step. Step 3b's security middleware (security-headers,
    # request-id/audit binding, rate-limiting, CORS — see create_app()) is
    # pure-ASGI/BaseHTTPMiddleware with no persistent resource of its own to
    # tear down (InMemoryBucketStore is a plain in-process dict, not a
    # connection), so there is nothing for it to add here.
    # -----------------------------------------------------------------------


def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Remaps FastAPI's native `RequestValidationError` (loc/msg/type list)
    into `ErrorEnvelope` at 422 — the exact remap error-envelope/README.md
    documents as Step 2's job (see "ONE error shape — including the native
    422" in that README)."""
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=ErrorCode.VALIDATION_FAILED,
            message="Request validation failed.",
            details=[
                ErrorDetail(field=".".join(str(p) for p in err["loc"]), message=err["msg"])
                for err in exc.errors()
            ],
        )
    )
    return JSONResponse(
        # HTTP_422_UNPROCESSABLE_ENTITY is deprecated in this pinned
        # Starlette line in favor of the RFC 9110 name below (same status
        # code, 422) — using the current constant avoids a
        # StarletteDeprecationWarning on every validation failure.
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=envelope.model_dump(mode="json"),
    )


def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Catches every `AppError` subclass (NotFoundError, ConflictError, ...)
    and renders `exc.to_envelope()` with `exc.status_code` — the
    per-subclass status/code table in error-envelope/README.md's "The
    exception hierarchy" section."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope().model_dump(mode="json"))


def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """JUDGMENT CALL (not explicitly required by Step 2's task list, added
    for defense-in-depth): catches anything that reaches here having
    escaped both handlers above — a genuine bug, not a deliberate AppError
    raise. error-envelope/errors.py's own module docstring describes this
    exact case ("an unhandled bug ... the framework's generic 500 handler
    still catches, mapping to this same base's to_envelope()"), so this
    keeps that promise literally true instead of leaving FastAPI's raw
    default 500 (a bare traceback in dev, an unenveloped generic message in
    prod) as the one place the app's error contract doesn't hold. Per
    references/backend/fastapi.md's "Validation & error handling" ("Never
    leak stack traces... return a safe message"), the client sees only
    `AppError`'s default internal-error message — never `str(exc)`."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=AppError().to_envelope().model_dump(mode="json"),
    )


def create_app(*, lifespan_ctx=lifespan, settings: Settings | None = None) -> FastAPI:
    """`lifespan_ctx` is overridable (defaults to the real `lifespan`
    above) purely so the hermetic test suite can substitute a lifespan that
    configures the engine against an already-shared in-memory sqlite
    connection instead of re-deriving DATABASE_URL from `Settings` — see
    tests/conftest.py. Never overridden outside tests.

    `settings` is overridable the same way, and for the same reason: the
    security-composition wiring below (rate limiting, CORS, security
    headers) needs a `Settings` instance at APP-CONSTRUCTION time now, not
    just inside `lifespan` at ASGI-startup time — see the module docstring's
    "Security composition" section. Defaults to `get_settings()` (the real,
    env-derived, `lru_cache`d instance) for every real boot, including this
    module's own `app = create_app()` below; the test suite passes an
    explicit `Settings(...)` instead, so a hermetic test app can configure a
    tiny `rate_limit_capacity` or a specific `cors_allowed_origins` without
    mutating process env vars (which would leak across tests) — see
    tests/conftest.py and tests/test_security_composition.py."""
    resolved_settings = settings if settings is not None else get_settings()

    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan_ctx,
    )

    app.include_router(health.router)
    app.include_router(items.router)
    app.include_router(auth.router)

    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    # --- Security composition (Stage 3 #26, Step 3b) ----------------------
    # See the module docstring's "Security composition" section for the
    # full outermost->innermost rationale and the add_middleware()-prepends-
    # then-reverses derivation. Calls below are ordered call-1-first
    # (innermost of the four) to call-4-last (outermost) — the OPPOSITE of
    # the module docstring's outermost-to-innermost prose order, because
    # that's what actually produces that runtime order.

    # Call 1 of 4 (innermost): CORS. Deny-by-default: `CORSPolicy.__init__`
    # itself refuses to construct with an empty `allow_origins` (see
    # cors_lockdown/_core.py's InsecureCORSPolicyError) — there is no
    # "allow nothing" policy object to build. Treating "no origins
    # configured" as "add no CORSMiddleware at all" is the deny-by-default
    # equivalent without hitting that guard on every dev/test boot where
    # cors_allowed_origins is unset: with no CORSMiddleware in the stack, no
    # Access-Control-Allow-Origin header is ever sent, so a browser blocks
    # every cross-origin JS request against this app regardless — the same
    # practical outcome as an explicit empty-allowlist policy would give.
    if resolved_settings.cors_allowed_origins:
        add_cors(app, CORSPolicy(allow_origins=tuple(resolved_settings.cors_allowed_origins)))

    # Call 2 of 4: rate limiting. One InMemoryBucketStore per app instance
    # (per-process, per rate_limiting/_core.py's own documented limitation —
    # see that file's "Judgment calls" for the multi-worker/multi-replica
    # caveat; Stage 11 swaps in a Redis-backed BucketStore for a true shared
    # ceiling). `trusted_hops` defaults to 0 (distrust X-Forwarded-For) —
    # see Settings.rate_limit_trusted_hops's own docstring for the exact,
    # per-environment opt-in this must never be guessed at.
    app.add_middleware(
        RateLimitMiddleware,
        store=InMemoryBucketStore(),
        capacity=resolved_settings.rate_limit_capacity,
        refill_per_second=resolved_settings.rate_limit_refill_per_second,
        trusted_hops=resolved_settings.rate_limit_trusted_hops,
    )

    # Call 3 of 4: request-id / audit binding. See audit_logging/
    # middleware.py's own docstring for the binding mechanics and the
    # client-supplied-X-Request-ID trust posture.
    app.add_middleware(RequestIDMiddleware)

    # Call 4 of 4 (outermost): security headers. Added LAST so it wraps
    # every other middleware and the router — see the module docstring's
    # point 1 for why that ordering specifically matters (it must see, and
    # be able to overwrite headers on, every response any lower layer
    # produces, including a 429 or a CORS preflight reply).
    add_security_headers(
        app,
        policy=SecurityHeadersPolicy(hsts_preload=resolved_settings.security_headers_hsts_preload),
    )
    # ------------------------------------------------------------------------

    return app


app = create_app()
