"""Hermetic settings for `manage.py check`/tests with no real database server
reachable — Django's sqlite3 backend (stdlib `sqlite3`, no extra driver
needed) standing in for backend/fastapi's aiosqlite hermetic-test posture.
Not vendored — new glue, this block's own test-settings seam.

Sets SECRET_KEY/DATABASE_URL to inert placeholder values BEFORE importing
`config.settings` so that module's own required-env-var guards are satisfied
without a caller having to export anything first, then overrides DATABASES
to sqlite3 unconditionally (real callers should still export SECRET_KEY
themselves for real use; the placeholder here only exists to satisfy the
"required, no default" guard for a purely local, no-secret sqlite check).

Usage: `DJANGO_SETTINGS_MODULE=config.settings_test python manage.py check`."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "hermetic-test-settings-placeholder-not-for-real-use")
os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")

from config.settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
