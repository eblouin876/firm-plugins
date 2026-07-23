"""Custom DRF `EXCEPTION_HANDLER` — Stage 4 Step 2 (#27), fix round —
mapping every exception DRF's view dispatch can raise onto
`core.contract.errors.ErrorEnvelope`, handler-for-handler mirroring
backend/fastapi's `app/main.py` (`_validation_exception_handler` +
`_app_error_handler` + `_make_unhandled_exception_handler`):

| Exception                                        | ErrorCode           | status            |
|---------------------------------------------------|---------------------|-------------------|
| `core.contract.errors.AppError` subclass           | `exc.code`          | `exc.status_code` |
| `core.security.auth.AuthError` subclass            | via `AUTH_ERROR_HTTP` (below) | via `AUTH_ERROR_HTTP` (below) |
| `rest_framework.exceptions.ValidationError`        | `validation_failed` | 422               |
| `NotFound` / `django.http.Http404`                 | `not_found`         | 404               |
| `NotAuthenticated`                                 | `unauthenticated`   | 401               |
| `PermissionDenied` (DRF or Django's own)           | `permission_denied` | 403               |
| `Throttled`                                        | `rate_limited`      | 429               |
| any OTHER `rest_framework.exceptions.APIException`  | mapped from `exc.status_code` — see below | `exc.status_code` (real, unchanged) |
| a genuine non-`APIException` bug (unhandled)       | `internal_error`    | 500               |

**Every `APIException` gets a real, mapped envelope — none of them fall
through to the 500 catch-all.** DRF's own exception hierarchy has more
concrete subclasses than the five matched explicitly above
(`AuthenticationFailed`, `ParseError` — malformed JSON — ,
`MethodNotAllowed`, `UnsupportedMediaType`, `NotAcceptable`, a bare
`APIException`, ...); the `isinstance(exc, drf_exceptions.APIException)`
branch below catches every one of those and maps `exc.status_code` onto
the best-fit `ErrorCode`: 401→`unauthenticated` (this is also where
`AuthenticationFailed` lands — bad/malformed credentials, distinct from
`NotAuthenticated`'s "no credentials at all", both correctly 401),
403→`permission_denied`, 404→`not_found`, 429→`rate_limited`,
5xx→`internal_error`, and every other 4xx (400 `ParseError`, 405
`MethodNotAllowed`, 415 `UnsupportedMediaType`, 406 `NotAcceptable`, ...)
→`validation_failed` — `ErrorCode` (core/contract/errors.py) has no
per-status member for each of these, so `validation_failed` is the
best-fit *code* while the *status* stays DRF's own real status (405 stays
405, never folded into a fake 422/400). Before this fix round every one of
these collapsed to a bare 500 `internal_error` — see this block's README,
"Conformance", for the now-accurate divergence note on where this can
still differ in exact status/code from FastAPI (framework-level
negotiation errors, not documented operations).

**422, not DRF's default 400**: DRF's own `ValidationError` defaults to
`status_code = 400`; FastAPI's `RequestValidationError` remap
(app/main.py) uses 422 — reproducing 422 here, NOT DRF's default, is what
this handler's `ValidationError` branch does (constructs the `Response`
itself rather than reusing DRF's default handler's status).

**`core.security.auth.AuthError` (Stage 5b, #44)**: the vendored auth
component (`core/security/auth/_core.py`) raises its OWN exception
hierarchy (`InvalidCredentials`, `InvalidToken`, `TokenReused`,
`EmailAlreadyExists` — plus that same component's Django adapter's own
`InsufficientRole`, `core/security/auth/django.py`, which also subclasses
`AuthError`), never `core.contract.errors.AppError`. This handler's
`isinstance(exc, AuthError)` branch — placed BEFORE the generic
`APIException`/catch-all branches below, mirroring `app/main.py`'s
`_auth_error_handler` registration order relative to FastAPI's own
catch-alls — looks up `AUTH_ERROR_HTTP.get(type(exc), (401,
"unauthenticated"))` (the vendored Django adapter's own exception ->
`(status, ErrorCode string)` table, `core/security/auth/django.py`) to
pick the status and code; an unmapped `AuthError` subclass (shouldn't
happen — every concrete subclass this app can raise has an entry) still
fails SAFELY CLOSED to 401 `unauthenticated`, never a 500 that would leak
"this specific auth exception type wasn't wired up."

FIX B (ported from backend/fastapi's Stage 5a whole-PR review, reproduced
here rather than rediscovered): the `unauthenticated` (401) bucket emits
a SINGLE fixed, generic client message ("Authentication failed."), never
`str(exc)` — see `_core.py`'s `TokenReused` docstring: "A client must not
be able to distinguish 'reuse was detected and your whole session was
killed' from 'this token was simply invalid' from the wire response
alone." `_core.py` raises genuinely distinct messages within that same
401 bucket (`TokenReused("...reuse detected -- the token family has been
revoked.")` vs `InvalidToken("Refresh token has expired.")`, etc.) —
echoing `str(exc)` straight to the client would let an attacker replaying
a stolen refresh token read "reuse detected" in the response body and
confirm their token was burned, directly violating that contract. Every
401 auth failure (bad password, unknown/expired/revoked/malformed token,
AND reuse) is therefore byte-identical on the wire. `conflict` (409,
`EmailAlreadyExists`) and `permission_denied` (403, `InsufficientRole`)
keep echoing `str(exc)` — neither carries a secret the way a
refresh-token failure's exact cause does. `str(exc)` remains available
server-side (it's still on `exc`, and this branch does NOT log it —
a client-caused 4xx auth failure is expected traffic, matching this
handler's own "Logging" section below) for anyone who needs it; this only
changes what reaches the CLIENT.

**`AuthNotConfiguredError` is deliberately NOT caught here.** It is a
plain `RuntimeError` subclass (`core/security/auth/stores.py`'s own
docstring explains why: a SERVER misconfiguration — an unset
`JWT_SIGNING_KEY` — not a client-caused auth failure), not part of the
`AuthError` hierarchy this branch matches on. It therefore falls straight
through every branch below to the final catch-all, rendering the generic
`internal_error` envelope at 500 — fail-closed, without this handler ever
having to special-case it.

**NEVER leak `str(exc)`**: no branch — including the `APIException` branch
and the final catch-all — ever includes the original exception's raw
message/type in the client-facing envelope for a genuinely unhandled bug;
same promise `error-envelope/errors.py`'s own module docstring makes ("an
unhandled bug ... the framework's generic 500 handler still catches,
mapping to this same base's `to_envelope()`") and `app/main.py`'s
`_unhandled_exception_handler` keeps literally true on the FastAPI side.
(A mapped `APIException`'s own `str(exc.detail)` DOES reach the client —
that message is DRF's own client-facing validation/negotiation text, not
an internal bug's message, the same way `ValidationError`'s branch above
already surfaces `exc.detail` today.)

**Logging**: `logger.exception(...)` — the real traceback, server-side
only — fires ONLY for a genuine 5xx: either the final catch-all (a
non-`APIException` bug) or an `APIException` whose own `status_code` is
itself 5xx. A client-caused 4xx (bad UUID, malformed JSON, wrong method,
bad auth, ...) is expected traffic, not an operability signal, and is
never logged at `exception` level.

Wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` = `"core.exceptions.
exception_handler"` (config/settings.py)."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response

from core.contract.errors import AppError, ErrorBody, ErrorCode, ErrorDetail, ErrorEnvelope
from core.security.auth import AUTH_ERROR_HTTP, AuthError

logger = logging.getLogger(__name__)

_VALIDATION_MESSAGE = "Request validation failed."


def _flatten_validation_errors(detail: Any, field_path: str = "") -> list[ErrorDetail]:
    """Flattens DRF's field-keyed `ValidationError.detail` (a `dict`/`list`
    tree of `rest_framework.exceptions.ErrorDetail` string subclasses) into
    `core.contract.errors.ErrorDetail` entries — the DRF-side counterpart
    to `app/main.py`'s `".".join(str(p) for p in err["loc"])` flattening of
    FastAPI's `RequestValidationError.errors()`. A top-level, non-field
    error (`raise ValidationError("message")`, `non_field_errors`) yields
    `field=None`/`field="non_field_errors"` respectively — same
    `field: str | None` shape `ErrorDetail` (core/contract/errors.py)
    declares."""
    details: list[ErrorDetail] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            sub_path = f"{field_path}.{key}" if field_path else str(key)
            details.extend(_flatten_validation_errors(value, sub_path))
    elif isinstance(detail, list):
        for item in detail:
            if isinstance(item, (dict, list)):
                details.extend(_flatten_validation_errors(item, field_path))
            else:
                details.append(ErrorDetail(field=field_path or None, message=str(item)))
    else:
        details.append(ErrorDetail(field=field_path or None, message=str(detail)))
    return details


def exception_handler(exc: Exception, context: dict) -> Response:
    """DRF's `EXCEPTION_HANDLER` contract: `(exc, context) -> Response |
    None`. This implementation always returns a `Response` — even the
    final catch-all branch — so an exception raised inside a DRF view
    dispatch NEVER falls through to DRF's own default handler or Django's
    generic error page; every error response this app sends is
    `ErrorEnvelope`-shaped, no exceptions (see this module's docstring
    table)."""

    if isinstance(exc, AppError):
        envelope = exc.to_envelope()
        return Response(envelope.model_dump(mode="json"), status=exc.status_code)

    if isinstance(exc, AuthError):
        # See this module's docstring, "core.security.auth.AuthError
        # (Stage 5b, #44)", for the full rationale -- placed BEFORE the
        # generic APIException/catch-all branches below (AuthError shares
        # no base class with drf_exceptions.APIException, so ordering
        # relative to THOSE specific branches doesn't change dispatch, but
        # this mirrors app/main.py's own registration-order posture and
        # keeps every AuthError subclass, present or future, handled here
        # rather than falling through to a generic 500).
        auth_status, auth_code_str = AUTH_ERROR_HTTP.get(type(exc), (401, ErrorCode.UNAUTHENTICATED.value))
        auth_code = ErrorCode(auth_code_str)
        # FIX B: a single, fixed, generic message for the whole
        # `unauthenticated` (401) bucket -- NEVER str(exc) -- so reuse
        # detection (TokenReused) is byte-indistinguishable from any other
        # invalid-refresh-token failure at the wire. 409 (conflict) and 403
        # (permission_denied) keep echoing str(exc): neither carries a
        # secret the way a refresh-token failure's exact cause does.
        auth_message = (
            "Authentication failed." if auth_code is ErrorCode.UNAUTHENTICATED else (str(exc) or "Authentication failed.")
        )
        auth_envelope = ErrorEnvelope(error=ErrorBody(code=auth_code, message=auth_message, details=None))
        return Response(auth_envelope.model_dump(mode="json"), status=auth_status)

    if isinstance(exc, drf_exceptions.ValidationError):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.VALIDATION_FAILED,
                message=_VALIDATION_MESSAGE,
                details=_flatten_validation_errors(exc.detail) or None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=422)

    if isinstance(exc, (drf_exceptions.NotFound, Http404)):
        envelope = ErrorEnvelope(
            error=ErrorBody(code=ErrorCode.NOT_FOUND, message=str(exc) or "Not found.", details=None)
        )
        return Response(envelope.model_dump(mode="json"), status=404)

    if isinstance(exc, drf_exceptions.NotAuthenticated):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.UNAUTHENTICATED,
                message=str(exc) or "Authentication is required.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=401)

    if isinstance(exc, (drf_exceptions.PermissionDenied, DjangoPermissionDenied)):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.PERMISSION_DENIED,
                message=str(exc) or "You do not have permission to perform this action.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=403)

    if isinstance(exc, drf_exceptions.Throttled):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.RATE_LIMITED,
                message="Too many requests. Please try again later.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=429)

    if isinstance(exc, drf_exceptions.APIException):
        # Every OTHER APIException subclass DRF's own dispatch can raise —
        # AuthenticationFailed, ParseError (malformed JSON), MethodNotAllowed,
        # UnsupportedMediaType, NotAcceptable, a bare APIException, or any
        # project-specific subclass — lands here rather than the catch-all
        # below. Map from the exception's OWN `status_code` (never hardcode
        # 500 for these) onto the best-fit ErrorCode; see this module's
        # docstring table for the full mapping and rationale.
        api_status = exc.status_code
        if api_status == 401:
            code = ErrorCode.UNAUTHENTICATED
        elif api_status == 403:
            code = ErrorCode.PERMISSION_DENIED
        elif api_status == 404:
            code = ErrorCode.NOT_FOUND
        elif api_status == 429:
            code = ErrorCode.RATE_LIMITED
        elif api_status >= 500:
            code = ErrorCode.INTERNAL_ERROR
        else:
            # 400 (ParseError), 405 (MethodNotAllowed), 415
            # (UnsupportedMediaType), 406 (NotAcceptable), and any other
            # 4xx `ErrorCode` has no dedicated member for: `validation_failed`
            # is the best-fit CODE, while `api_status` (below) keeps the
            # real, correct STATUS — 405 stays 405, not folded into 422/400.
            code = ErrorCode.VALIDATION_FAILED

        message = str(exc.detail) if exc.detail else exc.default_detail
        envelope = ErrorEnvelope(error=ErrorBody(code=code, message=str(message), details=None))

        if api_status >= 500:
            # A genuine 5xx APIException (a bare APIException, or a
            # project-specific subclass with a 5xx default) is still an
            # operability signal worth the real traceback server-side --
            # same posture as the non-APIException catch-all below. A 4xx
            # here is expected client traffic, never logged at this level.
            logger.exception("Unhandled 5xx APIException in DRF view", exc_info=exc)

        return Response(envelope.model_dump(mode="json"), status=api_status)

    # Anything else: a genuinely unhandled bug (NOT an APIException -- every
    # APIException subclass is mapped above, none reach here) -- collapsed
    # to internal_error/500, this catalog's error contract's shape for "an
    # unhandled bug" (error-envelope/errors.py's own module docstring).
    # Logged server-side (with the real traceback) for operability -- NEVER
    # in the client-facing envelope, which only ever gets AppError's own
    # generic default_message.
    logger.exception("Unhandled exception in DRF view", exc_info=exc)
    envelope = AppError().to_envelope()
    return Response(envelope.model_dump(mode="json"), status=500)
