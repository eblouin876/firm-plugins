"""App-specific settings: this project's own `Settings`, subclassing the
vendored `AppSettings` (app/core/settings.py, vendored from
templates/components/backend/settings/settings.py — see that file's header
note). NOT itself a vendored file — this is the per-project composition
point settings/README.md documents ("a project SUBCLASSES AppSettings"),
so it lives here rather than inside the vendored settings.py, keeping that
file byte-identical to its source for the freshness audit.

`get_settings()` is `lru_cache`d so `Depends(get_settings)` (or a plain
call from app/main.py's lifespan) doesn't re-read/re-validate the
environment on every call — matching the "fails fast at startup" intent:
the first construction either succeeds once or raises once, and every
subsequent call reuses that same validated instance. Tests that need a
different environment call `get_settings.cache_clear()` after changing env
vars (see tests/conftest.py).
"""

from __future__ import annotations

from functools import lru_cache

from app.core.settings import AppSettings


class Settings(AppSettings):
    """This project's concrete settings. Adds nothing beyond `AppSettings`
    yet — Step 2 has no settings-worthy config of its own beyond
    `database_url`/`environment`/`debug`/`cors_allowed_origins` (all
    inherited). `app_name`/`api_version` are static app metadata, not
    environment-sourced config, so they live as plain constants in
    app/main.py instead of here."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
