"""Package seam for this block's vendored contract sources — NOT itself a
vendored file (new glue, same pattern as backend/fastapi's
app/core/db/__init__.py). Re-exports the public names of `errors.py`,
`pagination.py`, and `secret_store.py` so the rest of this app imports
`from core.contract import ErrorEnvelope, Page, get_secret` rather than
reaching into each vendored module directly.

These three files define THE contract (Pydantic shapes + the AppError
hierarchy) this block's own DRF layer maps to; the actual DRF emission
(a custom EXCEPTION_HANDLER rendering ErrorEnvelope, a pagination class
emitting the Page shape) is Step 2's job, not this package's — see this
block's README, "Conformance".
"""

from __future__ import annotations

from .errors import (
    AppError,
    ConflictError,
    ErrorBody,
    ErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnauthenticatedError,
    ValidationFailedError,
)
from .pagination import Page, PageParams
from .secret_store import (
    MissingSecretsError,
    SecretNotFoundError,
    SecretShapeError,
    get_secret,
    validate_required,
)

__all__ = [
    "AppError",
    "ConflictError",
    "ErrorBody",
    "ErrorCode",
    "ErrorDetail",
    "ErrorEnvelope",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitedError",
    "UnauthenticatedError",
    "ValidationFailedError",
    "Page",
    "PageParams",
    "MissingSecretsError",
    "SecretNotFoundError",
    "SecretShapeError",
    "get_secret",
    "validate_required",
]
