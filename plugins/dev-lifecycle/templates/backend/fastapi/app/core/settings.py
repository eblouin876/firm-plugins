# Vendored from templates/components/backend/settings; keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.

"""Framework-neutral settings base: pydantic-settings `BaseSettings` with
env/`.env` loading, and a documented (not hard-wired) composition point
for `secret_store.get_secret` (see templates/components/security/
secrets-loading/). Pydantic v2 + pydantic-settings, pinned per
references/compatibility-matrix.md's Backend — Python row. Canon:
references/backend/pydantic.md ("Settings & secrets" — configuration comes
from pydantic-settings' BaseSettings; a misconfigured environment fails
fast at startup, not deep in a request).

Drop-in: copy this file into app/core/settings.py. Framework-neutral — no
FastAPI import; a Django project (Stage 4) can use pydantic-settings the
same way (it's independent of Django's own settings.py module, or a
project can bridge the two — out of scope here).

Composition point: this module deliberately does NOT import secret_store
(templates/components/security/secrets-loading/secret_store.py) directly —
that would hard-couple every settings field to that one component even for
a project that never installs it. Instead a project SUBCLASSES AppSettings
and wires a field's default to `secret_store.get_secret(...)` explicitly,
e.g.:

    from secret_store import get_secret  # app.core.security.secret_store once copied in

    class Settings(AppSettings):
        secret_key: str = Field(default_factory=lambda: get_secret("SECRET_KEY"))

pydantic-settings' own env-file loading already covers the common case (a
field with no default reads its env var from the process env or `.env`
directly); reach for the secret_store composition only when a field needs
secret_store's layered env-then-AWS-Secrets-Manager resolution, which
pydantic-settings' plain env lookup does not provide on its own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """The settings base every project subclasses with its own fields. A
    field with no default is REQUIRED — pydantic-settings raises a
    `ValidationError` naming every missing one at instantiation time (app
    startup), the equivalent of secrets-loading's `validate_required()`
    fail-fast contract, for whichever fields the *loader itself* is
    responsible for rather than secret_store's layered resolution.

    `extra="forbid"`: pydantic-settings' env source only maps process-env
    keys that match a DECLARED field name (respecting `env_prefix`) into
    the settings object — it does not vacuum up unrelated system env vars
    (`PATH`, `HOME`, ...) as extra fields, so `extra="forbid"` is safe here
    and catches a genuine misconfiguration (a typo'd key in `.env`, or a
    field renamed in code but not in the deployed environment) at startup
    instead of that key being silently ignored. Same reject-don't-drop
    posture as `input-validation`'s `StrictModel`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # Required — no default. A project without DATABASE_URL set (env or
    # .env) fails at AppSettings() construction, not on the first request
    # that touches the database.
    database_url: str

    cors_allowed_origins: list[str] = Field(
        default_factory=list,
        description="Explicit per-environment allowlist — never '*' combined with credentials. "
        "See references/security/secure-baseline.md's CORS lockdown section.",
    )
