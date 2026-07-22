<!--
block: components/backend/error-envelope  # catalog component
needs:
  - pydantic v2 (2.13.x): the sole runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row
exposes:
  - ErrorCode — the frozen, versioned StrEnum of every machine-matchable error code
  - ErrorEnvelope, ErrorBody, ErrorDetail — the {error: {code, message, details?}} shape, THE SINGLE error contract (every error class, including remapped request-boundary validation)
  - AppError and its concrete subclasses (UnauthenticatedError, PermissionDeniedError, NotFoundError, ValidationFailedError, ConflictError, RateLimitedError) — the exception hierarchy a framework's handler maps to the envelope
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# error-envelope

A framework-neutral, drop-in `errors.py`: THE standard error envelope
every response in this app uses — for every error class, with no second
shape for request-boundary validation — and the exception hierarchy a
framework's own exception handler maps to it. Lives at
`templates/components/backend/error-envelope/` in this repo; Stage 3
backend blocks copy `errors.py` verbatim into `app/core/errors.py`. THE
contract Step 2's FastAPI exception handler renders, and Stage 4's Django/
DRF track's own exception handler conforms to independently.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block. **Framework-neutral by design** —
no FastAPI import anywhere in this file; both Stage 3 and Stage 4 conform
to the shape below.

## Contents
- Composition contract
- The envelope shape (THE contract)
- ONE error shape — including the native 422
- The exception hierarchy
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Pydantic v2, 2.13.x** — the sole runtime dependency, pinned per
  `references/compatibility-matrix.md`'s Backend — Python row.

**EXPOSES**
- `ErrorCode` — a `StrEnum` of the frozen, machine-matchable code set
  (`internal_error`, `unauthenticated`, `permission_denied`, `not_found`,
  `validation_failed`, `conflict`, `rate_limited`). Extensible-but-
  versioned — see "The exception hierarchy" below.
- `ErrorEnvelope` / `ErrorBody` / `ErrorDetail` — the envelope shape (see
  below). `ErrorBody.code: ErrorCode`, not a bare `str`.
- `AppError` — the exception base every domain/HTTP-shaped error the app
  raises deliberately extends. `to_envelope() -> ErrorEnvelope`.
- Six concrete subclasses: `UnauthenticatedError` (401),
  `PermissionDeniedError` (403), `NotFoundError` (404),
  `ValidationFailedError` (422), `ConflictError` (409), `RateLimitedError`
  (429) — each with its own `code`, `status_code`, and `default_message`.
- Its co-located doc fragment: `docs/fragment.md`.

**Registered separately, not by this file:** the FastAPI (or Django/DRF)
exception handler that catches `AppError` and renders `exc.to_envelope()`
with `exc.status_code` is wired in Step 2's own app assembly — this
component ships the shape and the exception types only, deliberately with
no framework import or `except`-to-HTTP-response code here.

## The envelope shape (THE contract)

```python
class ErrorCode(StrEnum):
    INTERNAL_ERROR = "internal_error"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    VALIDATION_FAILED = "validation_failed"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"

class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str | None = None
    message: str

class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ErrorCode
    message: str
    details: list[ErrorDetail] | None = None

class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorBody
```

Serialized:

```json
{"error": {"code": "not_found", "message": "The requested resource was not found.", "details": null}}
```

A client switches on `code` (typed as `ErrorCode`, so OpenAPI emits it as
an enum and a generated client gets an exhaustive union), never on
`message` — `message` is for humans and can change wording without
breaking a client. `details` is a list of `{field, message}` pairs for a
failure with more than one thing to say (e.g. several business rules
violated at once); `field` is optional since not every detail ties to a
single field.

## ONE error shape — including the native 422

FastAPI/Pydantic's own automatic response for a request-body or
query-param schema validation failure — `{"detail": [{"loc": [...], "msg":
..., "type": ...}]}` — is FastAPI's built-in behavior, produced before the
app's own exception handler ever runs. It is **not this app's contract**:
DRF has no way to reproduce that native shape, so a Django backend
(Stage 4) claiming wire-for-wire parity with the FastAPI track (Step 2)
would break the moment a client actually hit a validation error. Instead,
THE contract is a single shape for every error class, including this one:

Step 2's FastAPI app **must** register a `RequestValidationError` handler
that remaps FastAPI's native validation errors into `ErrorEnvelope` before
they reach a client:

```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
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
    return JSONResponse(status_code=422, content=envelope.model_dump())
```

Stage 4's Django/DRF track maps DRF's own `ValidationError` into the
identical envelope + 422 independently (no shared code, just the same
target shape) — that's what makes "Django conforms wire-for-wire" true.
The app-raised `ValidationFailedError` below carries the same `code`
(`validation_failed`) and the same status (422), so a client sees exactly
one error shape and one status for "the request didn't validate,"
regardless of whether FastAPI's own request-boundary validation caught it
or a service function raised `ValidationFailedError` for a business rule a
schema can't express. `references/backend/fastapi.md`'s "Validation &
error handling" section ("Let schema validation reject malformed input
automatically (422)... Add exception handlers for domain exceptions") is
the canon this remap is grounded in — this component only ships the
target shape; registering the actual `RequestValidationError` handler is
Step 2's job, not this file's (kept out of this file to stay FastAPI-
import-free, per the module docstring). Regenerating the API client
against the single shape is Step 4's job.

## The exception hierarchy

`AppError(message: str | None = None, *, details: list[ErrorDetail] |
None = None)` — subclass per error class, don't raise `AppError` directly
in application code:

| Exception | `code` | `status_code` |
| --- | --- | --- |
| `UnauthenticatedError` | `unauthenticated` | 401 |
| `PermissionDeniedError` | `permission_denied` | 403 |
| `NotFoundError` | `not_found` | 404 |
| `ValidationFailedError` | `validation_failed` | 422 (matches the remapped native 422 — see "ONE error shape" above) |
| `ConflictError` | `conflict` | 409 |
| `RateLimitedError` | `rate_limited` | 429 |
| `AppError` (base, raised directly only for an unhandled/generic case) | `internal_error` | 500 |

`UnauthenticatedError` vs `PermissionDeniedError` matches
`references/security/secure-baseline.md`'s "Authentication &
authorization" distinction: authentication proves identity (401 — no
valid credentials at all); authorization checks whether *this* identity
may act on *this* resource (403 — authenticated, but not allowed).
`RateLimitedError` exists so the middleware/rate-limit component (Stage 2)
can raise a 429 through this same envelope shape instead of hand-rolling
its own body.

## Testing

`tests/test_errors.py` covers: the envelope's exact serialized shape
(including the `details: null` omission case), a populated `details` list,
`ErrorDetail.field` being optional, all three models rejecting an unknown
field (`extra="forbid"`), `AppError`'s default-vs-custom message and
`to_envelope()` round trip, `AppError` behaving as a real raisable
exception, `to_envelope()` carrying `details` through, every concrete
subclass's `code`/`status_code`/non-empty default message (parametrized
across all six, `ValidationFailedError` asserting 422), a concrete
subclass's full serialized envelope, a concrete subclass accepting a
custom message, every concrete subclass being an `AppError`, `ErrorCode`
having exactly the seven canonical members, `ErrorCode` being a `str`
subclass that serializes as a plain string (both `model_dump()` and
`model_dump_json()`), `ErrorBody` coercing a valid code string into the
enum, and `ErrorBody` rejecting an unrecognized code string.

Run: `uv run --python 3.13 --with 'pydantic==2.13.*' --with pytest -- pytest templates/components/backend/error-envelope/tests/ -q`

## Judgment calls

- **Six concrete subclasses, not a generic `AppError(code=..., status_code=...)`
  constructor call site.** A named class per error class
  (`NotFoundError`, `ConflictError`, ...) makes `except NotFoundError:` and
  `raise NotFoundError(...)` both readable and greppable across the
  codebase; a single parametrized `AppError` would work but loses that at
  every call and catch site.
- **`RateLimitedError` lives here, not in the middleware/rate-limit
  component (Stage 2).** The rate-limit middleware raises it, but the
  *exception type* belongs with the rest of the hierarchy so every error
  class stays in one place with one shared `to_envelope()` mechanism,
  rather than splitting the hierarchy across two components.
- **The FastAPI/Django exception-handler registration is explicitly out of
  scope for this file.** Keeping this component importable with zero
  framework dependency is what lets Stage 4's Django/DRF track reuse the
  exact same `AppError` hierarchy and envelope shape — a hard FastAPI
  import here would break that reuse.
- **`ErrorCode` is a `StrEnum`, not a `Literal[...]` union.** Either would
  give OpenAPI an enum; `StrEnum` was chosen so the members are also
  addressable as real attributes (`ErrorCode.NOT_FOUND`) at every call
  site across this component's own subclasses and any future consumer,
  rather than callers re-typing string literals that could drift from the
  canonical set.
- **`ValidationFailedError` carries 422, not 400.** Before this fix it
  used 400, which meant an app-raised domain validation failure and a
  FastAPI request-boundary validation failure (422, un-enveloped)
  disagreed on both status and shape. Now both use 422 and the same
  envelope — the FastAPI-native 422 shape is explicitly overridden by
  Step 2's `RequestValidationError` remap so there is exactly one
  validation-failure contract, not two.
