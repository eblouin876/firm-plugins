<!-- fragment: block:components/backend/error-envelope -->

## Setup
Copy `errors.py` into `app/core/errors.py`. Raise the concrete `AppError`
subclass matching the failure (`NotFoundError`, `ConflictError`, ...)
anywhere in a service/route; register a framework exception handler
(FastAPI's `add_exception_handler(AppError, ...)`, or a Django/DRF
`exception_handler`) that catches `AppError` and renders
`exc.to_envelope().model_dump()` with `exc.status_code` — that handler is
wired in Step 2, not this file. Step 2 **must also** register a FastAPI
`RequestValidationError` handler that remaps the native 422 shape into
`ErrorEnvelope` (`code=ErrorCode.VALIDATION_FAILED`, status 422) — see the
README's "ONE error shape — including the native 422" for the exact remap
and rationale; without it, Django's DRF track cannot conform wire-for-wire
since DRF has no way to reproduce FastAPI's native `{"detail": [...]}`
shape.

## Maintenance
Framework-neutral by design: no FastAPI import in this file. This is THE
error contract both the FastAPI (Stage 3) and Django/DRF (Stage 4) tracks
conform to — a single shape for every error class, `ErrorCode` is a frozen
but extensible enum, and `ValidationFailedError` shares 422 with the
remapped native validation error.
