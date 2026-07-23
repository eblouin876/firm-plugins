"""Custom DRF `EXCEPTION_HANDLER` — Stage 4 Step 2 (#27), fix round —
mapping every exception DRF's view dispatch can raise onto
`core.contract.errors.ErrorEnvelope`, handler-for-handler mirroring
backend/fastapi's `app/main.py` (`_validation_exception_handler` +
`_app_error_handler` + `_make_unhandled_exception_handler`):

| Exception                                        | ErrorCode           | status            |
|---------------------------------------------------|---------------------|-------------------|
| `core.contract.errors.AppError` subclass           | `exc.code`          | `exc.status_code` |
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
