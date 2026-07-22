"""Package seam for the vendored secrets-loading component (`secret_store.py`
— vendored from templates/components/security/secrets-loading/, see that
file's own header note). This component ships as a single flat file with no
cross-imports to adapt (unlike security_headers/cors_lockdown/rate_limiting,
which pair a `_core.py` with a `fastapi.py`), so it needs no relative-import
rewrite — `secret_store.py` is byte-identical below its header. It still
lands as its own subpackage (this directory) rather than a bare
`app/core/security/secret_store.py` module, for the same reason every other
vendored security component does: a consistent, self-contained-subpackage
shape across app/core/security/, per README.md's "Vendored components"
invariant, rather than a mix of directories and bare files.

Re-exports the names app/core/config.py's `Settings` (the secrets
composition seam — see that file's `jwt_signing_key` field) and any other
caller need, so callers write `from app.core.security.secret_store import
get_secret` instead of `from app.core.security.secret_store.secret_store
import get_secret`.
"""

from __future__ import annotations

from .secret_store import (
    MissingSecretsError,
    SecretNotFoundError,
    SecretShapeError,
    SecretsManagerClient,
    get_secret,
    validate_required,
)

__all__ = [
    "MissingSecretsError",
    "SecretNotFoundError",
    "SecretShapeError",
    "SecretsManagerClient",
    "get_secret",
    "validate_required",
]
