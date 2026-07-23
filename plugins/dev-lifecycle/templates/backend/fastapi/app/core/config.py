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

Stage 3 Step 3b (#26): adds the config the security-composition wiring in
app/main.py's create_app() needs (rate limiting, security headers) plus one
concrete secret_store composition example (`jwt_signing_key`) — see each
field's own docstring below for its default and why.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from app.core.security.secret_store import get_secret
from app.core.settings import AppSettings


class Settings(AppSettings):
    """This project's concrete settings. `app_name`/`api_version` are
    static app metadata, not environment-sourced config, so they live as
    plain constants in app/main.py instead of here."""

    # --- Rate limiting (rate_limiting/fastapi.py's RateLimitMiddleware,
    # wired in app/main.py's create_app()) -----------------------------
    rate_limit_capacity: int = Field(
        default=60,
        description="Token-bucket capacity for the general per-IP API ceiling "
        "(rate_limiting/README.md's 'the general per-IP API ceiling'). 60 is a "
        "starting-point default, not a load-tested figure -- tune per project.",
    )
    rate_limit_refill_per_second: float = Field(
        default=1.0,
        description="Tokens refilled per second -- 1.0 pairs with capacity=60 for "
        "a nominal ~60/minute steady-state ceiling with a 60-request burst "
        "allowance. See rate_limiting/_core.py's 'refill_per_second as a float' "
        "judgment call for why this isn't 'N requests per window' instead.",
    )
    rate_limit_trusted_hops: int = Field(
        default=0,
        description="SECURE DEFAULT: 0 -- distrust X-Forwarded-For entirely and "
        "key on the real TCP peer address, per rate_limiting/_core.py's "
        "client_ip_key(). Set to the EXACT number of trusted reverse proxies "
        "directly in front of this app (e.g. 1 for a single ALB) once that "
        "topology is confirmed for a given environment -- never guessed, and "
        "never left at a default '>0' value, which would let a client spoof "
        "its own rate-limit key via a forged header.",
    )

    # --- Security headers (security_headers/fastapi.py's
    # add_security_headers, wired in app/main.py's create_app()) --------
    security_headers_hsts_preload: bool = Field(
        default=False,
        description="SECURE DEFAULT: False, matching security_headers/_core.py's "
        "own SecurityHeadersPolicy default. HSTS preload is a one-way door (the "
        "browser preload list) -- opt in deliberately per environment once HTTPS "
        "is confirmed correct everywhere on this domain, never by default.",
    )

    # --- Secrets composition seam (Stage 5, #28) ------------------------
    # settings.py's own module docstring documents this exact composition
    # pattern ("a project SUBCLASSES AppSettings and wires a field's default
    # to secret_store.get_secret(...)"); this is that pattern's one concrete
    # example for this block. `required=False` and no invented fallback
    # value: nothing in this app consumes jwt_signing_key yet (Stage 5 wires
    # real JWT issuance), so this resolves to `None` in dev/test today
    # rather than either (a) making Settings() construction fail wherever
    # JWT_SIGNING_KEY isn't set -- which would break every existing test and
    # the plain `uvicorn app.main:app` dev boot, both of which predate this
    # field and don't set it -- or (b) hard-coding a fake "dev" secret value,
    # which is exactly the "don't invent secrets" this seam is scoped to
    # avoid. `repr=False`/`exclude=True` so a resolved value (once Stage 5
    # sets JWT_SIGNING_KEY for real) never appears in a `Settings` repr, a
    # `model_dump()`, or a traceback that happens to print `self` -- the
    # same "never log a secret value" posture secret_store.py's own
    # docstring establishes, applied here at the settings-object boundary.
    jwt_signing_key: str | None = Field(
        default_factory=lambda: get_secret("JWT_SIGNING_KEY", required=False),
        repr=False,
        exclude=True,
        description="Stage 5a (#41) JWT signing key, resolved via "
        "secret_store.get_secret's layered env-then-AWS-Secrets-Manager "
        "resolution. Still resolves to None when JWT_SIGNING_KEY is unset -- "
        "most of this app's routes/tests never touch auth at all, so "
        "Settings() construction must not hard-fail on a missing secret this "
        "request doesn't need. app/core/security/auth/stores.py's "
        "get_token_service() is where the fail-CLOSED check actually lives: "
        "it refuses to construct a TokenService (and therefore refuses to "
        "sign/verify anything) when this is None, at the point auth is "
        "actually used, not at Settings() construction time.",
    )

    # --- Auth (Stage 5a, #41): the vendored auth component's TokenService,
    # constructed in app/core/security/auth/stores.py:get_token_service()
    # from the three fields below plus jwt_signing_key above -----------
    jwt_issuer: str = Field(
        default="app",
        description="The `iss` claim TokenService stamps into every minted "
        "JWT and requires on every decode (_core.py's TokenService.decode_* "
        "-- see its own docstring on why issuer is checked, not just "
        "signature/expiry). A generic default; a project with more than one "
        "issuer sharing a signing key (rare) would override this per "
        "environment -- most projects never need to.",
    )
    jwt_access_ttl_seconds: int = Field(
        default=900,
        description="Access token TTL, 15 minutes -- short-lived by design "
        "(references/security/secure-baseline.md: 'Prefer short-lived "
        "access tokens with refresh over long-lived static tokens'). A "
        "stolen access token's blast radius is bounded by this window; "
        "there is no server-side revocation for access tokens themselves "
        "(only refresh tokens are revocable, via RefreshTokenStore).",
    )
    jwt_refresh_ttl_seconds: int = Field(
        default=1_209_600,
        description="Refresh token TTL, 14 days (1_209_600 seconds) -- long "
        "enough that a legitimate user isn't forced to re-login constantly, "
        "short enough to bound how long a family that somehow evades reuse "
        "detection could stay alive. Refresh tokens ARE individually "
        "revocable (RefreshTokenStore.revoke_family, on reuse detection or "
        "logout), unlike access tokens above -- this TTL is a ceiling on top "
        "of that, not the only defense.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
