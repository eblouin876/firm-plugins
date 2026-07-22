"""`create_app()` factory: registers routers, registers the two exception
handlers the `error-envelope` contract requires (RequestValidationError ->
ErrorEnvelope 422; AppError hierarchy -> ErrorEnvelope with each
subclass's own status/code), and configures OpenAPI metadata + the bearer
security scheme for the Stage 5 auth seam. CORS/security middleware is
explicitly a Step 3 TODO — see the comment in `create_app()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routers import auth, health, items
from app.core.config import get_settings
from app.core.db import configure_engine
from app.core.errors import AppError, ErrorBody, ErrorCode, ErrorDetail, ErrorEnvelope

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
    # --- Step 3 TODO -----------------------------------------------------
    # Graceful engine disposal (`await get_engine().dispose()`) and any
    # security-middleware teardown land here once Step 3 vendors those
    # components. Left as a no-op shutdown for now rather than guessing at
    # what that teardown needs.
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


def create_app(*, lifespan_ctx=lifespan) -> FastAPI:
    """`lifespan_ctx` is overridable (defaults to the real `lifespan`
    above) purely so the hermetic test suite can substitute a lifespan that
    configures the engine against an already-shared in-memory sqlite
    connection instead of re-deriving DATABASE_URL from `Settings` — see
    tests/conftest.py. Never overridden outside tests."""
    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan_ctx,
    )

    # --- Step 3 TODO -----------------------------------------------------
    # No CORSMiddleware, security-headers middleware, or rate limiting is
    # wired here yet. Security-component vendoring is Step 3's job (Stage 3
    # issue #26) — this factory deliberately stops short of guessing at
    # that wiring so Step 3 has a clean seam to fill, per
    # references/security/secure-baseline.md's "CORS lockdown" and
    # "Security headers & CSP" sections.
    # -----------------------------------------------------------------------

    app.include_router(health.router)
    app.include_router(items.router)
    app.include_router(auth.router)

    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    return app


app = create_app()
