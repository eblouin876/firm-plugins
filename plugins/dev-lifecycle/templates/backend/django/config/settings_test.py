"""Hermetic settings for `manage.py check`/tests with no real database server
reachable — Django's sqlite3 backend (stdlib `sqlite3`, no extra driver
needed) standing in for backend/fastapi's aiosqlite hermetic-test posture.
Not vendored — new glue, this block's own test-settings seam.

Sets SECRET_KEY/DATABASE_URL/JWT_SIGNING_KEY to inert placeholder values
BEFORE importing `config.settings` so that module's own required-env-var
guards are satisfied without a caller having to export anything first, then
overrides DATABASES to sqlite3 unconditionally (real callers should still
export SECRET_KEY/JWT_SIGNING_KEY themselves for real use; the placeholders
here only exist to satisfy the "required, no default" guard for a purely
local, no-secret sqlite check).

Usage: `DJANGO_SETTINGS_MODULE=config.settings_test python manage.py check`."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "hermetic-test-settings-placeholder-not-for-real-use")
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")
# Stage 5b (#44): unlike SECRET_KEY/DATABASE_URL above, config/settings.py's
# JWT_SIGNING_KEY is NOT required (`_get_secret(..., required=False)` —
# resolves to `None` when unset, matching backend/fastapi's identical
# `jwt_signing_key: str | None` posture). A placeholder is set here anyway
# so `tests/test_auth_stores.py` (Step 6) — and any hermetic test that
# actually exercises `get_token_service()`/`build_auth_service()` — has a
# real (non-`None`) signing key to construct a `TokenService` against
# without every such test having to set the env var itself; the JWT/access/
# refresh TTL defaults (JWT_ISSUER="app", JWT_ACCESS_TTL_SECONDS=900,
# JWT_REFRESH_TTL_SECONDS=1209600) already need no override for a hermetic
# run, so only JWT_SIGNING_KEY needs a value set here.
os.environ.setdefault("JWT_SIGNING_KEY", "hermetic-test-jwt-signing-key-placeholder-not-for-real-use")

from config.settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
