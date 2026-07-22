"""Framework-neutral error envelope: THE single error shape every error
response in this app uses — including the framework's own request-
boundary validation failures — plus the exception hierarchy a framework's
exception handler maps to it. Pydantic v2 only (pinned per
references/compatibility-matrix.md's Backend — Python row to Pydantic v2,
2.13.x) — NO FastAPI import in this file (shape only). This is THE
contract Stage 3's FastAPI exception handler (Step 2) and Stage 4's Django/
DRF exception handler both map their errors to, and what any API client
conforms to when parsing an error response.

Drop-in: copy this file into app/core/errors.py. The FastAPI exception
handler that catches AppError subclasses and renders ErrorEnvelope as the
JSON body is registered separately, in Step 2's app/core/exceptions.py (or
wherever that block's own FastAPI wiring lands) — this file is the shape
and the exception types only, deliberately with no `except`-to-HTTP
mapping or FastAPI import here, so a Django/DRF exception handler (Stage 4)
can import the same AppError hierarchy without pulling in FastAPI.

ONE error shape, not two: FastAPI/Pydantic's own automatic response for a
request-body/query-param schema validation failure — the native shape
`{"detail": [{"loc": [...], "msg": ..., "type": ...}]}` — is NOT part of
this app's contract; DRF has no way to reproduce that shape, and "Django
conforms wire-for-wire" would break the moment a client saw it. Step 2's
FastAPI app MUST register a `RequestValidationError` handler that remaps
FastAPI's native validation errors into THIS envelope before they ever
reach a client:

    ErrorEnvelope(
        error=ErrorBody(
            code=ErrorCode.VALIDATION_FAILED,
            message=<a summary, e.g. "Request validation failed.">,
            details=[
                ErrorDetail(field=".".join(str(p) for p in err["loc"]), message=err["msg"])
                for err in exc.errors()
            ],
        )
    ), returned with status 422

Stage 4's Django/DRF track maps DRF's own `ValidationError` into the
identical envelope + 422, independently — achieving wire-for-wire parity
with Step 2's remap without importing FastAPI or this file's Step 2
counterpart. `ValidationFailedError` below (the domain-level, non-schema
validation failure this app raises deliberately) carries the SAME status
(422) and the SAME `code` (`validation_failed`) as that remap, so a client
parsing an error response only ever sees ONE shape and ONE status for
"the request didn't validate" — whether the failure was caught at the
request boundary or inside a service function. (Actually registering that
FastAPI handler is Step 2's job, not this file's; regenerating the API
client to reflect the single shape is Step 4's job — this docstring only
keeps the CONTRACT docs consistent with what those steps must do.)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# The error code enum (THE closed, versioned set)
# ---------------------------------------------------------------------------


class ErrorCode(StrEnum):
    """THE closed set of machine-matchable error codes this app's
    `ErrorEnvelope` ever carries. A `StrEnum` (not a bare `str` field) so
    OpenAPI emits a proper enum for `ErrorBody.code` — a generated API
    client gets an exhaustive union to switch on, not an unconstrained
    string. Members align 1:1 with the concrete `AppError` subclasses
    below (plus `internal_error`, the base's default); the exact string
    values already in use are preserved unchanged so this is a type
    tightening, not a wire-format change.

    Extensible-but-versioned: adding a new member is additive for a client
    with a default/fallback case, but is a breaking change for a strict
    generated client that exhaustively switches over every existing
    member. Treat adding, renaming, or removing a member as a contract
    change requiring the same coordination as any other wire-shape edit —
    bump the generated API client (Step 4), and keep Stage 4's Django/DRF
    exception handler's own code set aligned with this one."""

    INTERNAL_ERROR = "internal_error"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    VALIDATION_FAILED = "validation_failed"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"


# ---------------------------------------------------------------------------
# The envelope shape (THE contract)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """One item in an error's optional `details` list — e.g. one field's
    domain-level problem inside a larger validation failure. `field` is
    optional: some details aren't tied to a single field (a cross-field
    business rule, a resource-level conflict note)."""

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    """The `error` object inside the envelope. `code` is a short, stable,
    machine-matchable `ErrorCode` member — a client should switch on
    `code`, never on `message` (message is for humans, can change wording
    without breaking a client, and MUST NOT be treated as a stable
    identifier). Typed as `ErrorCode`, not `str`, so Pydantic rejects an
    unrecognized code at construction time and OpenAPI documents the
    closed set."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: list[ErrorDetail] | None = None


class ErrorEnvelope(BaseModel):
    """THE error envelope every error response in this app uses — every
    non-2xx error, including request-boundary validation failures once
    Step 2's `RequestValidationError` handler remaps them (see this
    module's docstring):

        {"error": {"code": "not_found", "message": "...", "details": null}}

    Every field required except `details`, which is `null` (omitted from
    the exception's own `to_envelope()` output) when there's nothing more
    specific than the top-level `code`/`message` to say."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


# ---------------------------------------------------------------------------
# The exception hierarchy a framework's handler maps to the envelope
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base of every domain/HTTP-shaped exception the app raises
    deliberately (as opposed to an unhandled bug, which the framework's
    generic 500 handler still catches, mapping to this same base's
    `to_envelope()` — see `code`/`status_code`'s defaults below).

    A framework's exception handler (Step 2's FastAPI wiring, or a Django/
    DRF `exception_handler`) catches `AppError` and renders
    `exc.to_envelope()` as the JSON body with `exc.status_code`. Subclass
    per error class (see the concrete ones below) rather than raising
    `AppError` directly in application code — the concrete subclasses are
    what carry the right `code`/`status_code`/default message."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: list[ErrorDetail] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(error=ErrorBody(code=self.code, message=self.message, details=self.details))


class UnauthenticatedError(AppError):
    """No valid credentials presented at all — distinct from
    `PermissionDeniedError` (authenticated, but not allowed). Per
    references/security/secure-baseline.md's "Authentication &
    authorization": authentication proves identity; authorization checks
    whether *this* identity may act on *this* resource."""

    code = ErrorCode.UNAUTHENTICATED
    status_code = 401
    default_message = "Authentication is required."


class PermissionDeniedError(AppError):
    """Authenticated, but not authorized for this action/resource — the
    IDOR-class check (`references/security/secure-baseline.md`: "Check
    ownership/scope on every ID-addressed resource")."""

    code = ErrorCode.PERMISSION_DENIED
    status_code = 403
    default_message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    status_code = 404
    default_message = "The requested resource was not found."


class ValidationFailedError(AppError):
    """A domain-level validation failure that is NOT a schema mismatch —
    e.g. a business-rule violation a field constraint can't express
    ("end_date must be after start_date") caught in a service function,
    not at the schema layer. Carries the SAME status (422) and the SAME
    `code` (`validation_failed`) as Step 2's FastAPI `RequestValidationError`
    remap and Stage 4's DRF `ValidationError` mapping (see this module's
    docstring) — app-raised and request-boundary validation failures are
    indistinguishable to a client past the envelope: both render as
    `{"error": {"code": "validation_failed", ...}}` at 422, THE single
    error shape and status for "the request didn't validate"."""

    code = ErrorCode.VALIDATION_FAILED
    status_code = 422
    default_message = "The request could not be validated."


class ConflictError(AppError):
    """The requested change conflicts with the resource's current state
    (a duplicate unique key, a stale optimistic-concurrency version, a
    state-machine transition that isn't valid from the current state)."""

    code = ErrorCode.CONFLICT
    status_code = 409
    default_message = "The request conflicts with the current state of the resource."


class RateLimitedError(AppError):
    """Caller has exceeded a rate limit. Per
    references/security/secure-baseline.md's "Rate limiting & lockout" —
    the middleware/rate-limit component (Stage 2) raises this rather than
    hand-rolling its own 429 body, so a rate-limited response uses the
    same envelope shape as every other error."""

    code = ErrorCode.RATE_LIMITED
    status_code = 429
    default_message = "Too many requests. Please try again later."
