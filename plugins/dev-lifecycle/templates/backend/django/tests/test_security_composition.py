"""Security-composition proof — Stage 4 Step 3 (#27), commit 2: verifies the
MIDDLEWARE stack config/settings.py wires (see that file's "Security
composition" docstring for the full order/rationale) actually does what it
claims on a real request/response round-trip, not just at the unit level
each vendored component's own tests/ already cover in
templates/components/security/*/tests/.

Uses `/health` (no auth, no DB write) as the probe route throughout, except
where a distinct route is needed: JSONRenderer-only uses `/items` (the one
route with a browsable-API-relevant list action), and the rate-limiting
tests ALSO use `/items` instead of `/health` -- Stage 4 review fix, #27:
`/health`/`/readyz` are now exempt from rate limiting entirely (`core/
security/rate_limiting/django.py`'s `_DEFAULT_EXEMPT_PATHS` -- a readiness
probe must never be 429'd), so `/health` can no longer be used to prove
rate-limiting behavior; `/items` (not exempt) is the probe for those two
tests instead.

The shared module-level `_default_store` singleton
(`core.security.rate_limiting.django._default_store`) is reset before every
test in this suite by the autouse `_reset_rate_limit_store` fixture
(`tests/conftest.py`) — see that fixture's own docstring for why (a
process-wide bucket keyed on the test client's constant REMOTE_ADDR would
otherwise leak state, and 429s, across unrelated tests). The rate-limiting
tests below still construct a fresh `APIClient()` AFTER overriding
`RATE_LIMIT_*` settings, since `RateLimitMiddleware` reads them at
`__init__` time (not per-request — Django instantiates a MIDDLEWARE entry
with only `get_response`, no way to pass per-request kwargs) and each new
`APIClient()`/`Client()` rebuilds its own middleware chain from current
settings (`django.test.Client.__init__` constructs a fresh `ClientHandler`
each time)."""

from __future__ import annotations

import re

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# security-headers
# ---------------------------------------------------------------------------


def test_security_headers_present_on_normal_response(api_client: APIClient) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=(), browsing-topics=(), interest-cohort=()"
    )
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'"
    )


def test_hsts_present_only_when_request_is_secure(api_client: APIClient) -> None:
    insecure = api_client.get("/health", secure=False)
    secure = api_client.get("/health", secure=True)

    assert "Strict-Transport-Security" not in insecure.headers
    assert secure.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_security_headers_win_over_django_own_security_middleware(api_client: APIClient) -> None:
    """Django's own `django.middleware.security.SecurityMiddleware` runs in
    this stack too (MIDDLEWARE, config/settings.py) but with
    SECURE_CONTENT_TYPE_NOSNIFF/SECURE_HSTS_SECONDS/SECURE_REFERRER_POLICY
    all off (settings.py's "Transport security headers" section) — it sets
    none of this header set itself, so there is nothing for our component
    to "win" against in practice today. What this test actually proves:
    the header values match _core.DEFAULT_POLICY exactly, i.e. nothing
    downstream (a view, DRF, Django's own middleware) is mutating them."""
    response = api_client.get("/health", secure=True)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


# ---------------------------------------------------------------------------
# cors-lockdown
# ---------------------------------------------------------------------------


def test_cors_preflight_from_disallowed_origin_gets_no_allow_header(
    api_client: APIClient, settings
) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://app.example.com"]

    response = api_client.options(
        "/health",
        HTTP_ORIGIN="https://evil.example.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_preflight_from_allowed_origin_gets_the_allow_header(
    api_client: APIClient, settings
) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://app.example.com"]

    response = api_client.options(
        "/health",
        HTTP_ORIGIN="https://app.example.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"


def test_cors_denies_every_origin_when_unconfigured(api_client: APIClient, settings) -> None:
    """Deny-by-default: this block's own settings.py leaves
    CORS_ALLOWED_ORIGINS unset when CORS_ALLOWED_ORIGINS the env var is
    empty (settings.py's "CORS" section) -- verified here directly against
    django-cors-headers' own default (an empty CORS_ALLOWED_ORIGINS list),
    which is what a project that never sets the env var actually gets."""
    settings.CORS_ALLOWED_ORIGINS = []

    response = api_client.options(
        "/health",
        HTTP_ORIGIN="https://anything.example.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert "Access-Control-Allow-Origin" not in response.headers


# ---------------------------------------------------------------------------
# rate-limiting
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after_once_burst_exhausted(settings) -> None:
    settings.RATE_LIMIT_CAPACITY = 2
    settings.RATE_LIMIT_REFILL_PER_SECOND = 0.0001  # effectively no refill within this test's runtime
    client = APIClient()  # constructed AFTER the settings override, see module docstring

    first = client.get("/items")
    second = client.get("/items")
    third = client.get("/items")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["Retry-After"] is not None
    assert int(third.headers["Retry-After"]) >= 1


def test_rate_limit_does_not_deny_a_fresh_capacity_budget(settings) -> None:
    settings.RATE_LIMIT_CAPACITY = 60
    settings.RATE_LIMIT_REFILL_PER_SECOND = 1.0
    client = APIClient()

    response = client.get("/items")

    assert response.status_code == 200
    assert "Retry-After" not in response.headers


def test_health_and_readyz_are_never_rate_limited_even_under_burst(settings) -> None:
    """Stage 4 review fix (#27): `/health`/`/readyz` are exempt from rate
    limiting (`core/security/rate_limiting/django.py`'s `_DEFAULT_EXEMPT_
    PATHS`) so a load balancer's readiness/liveness probe can never be
    429'd into a false-unhealthy signal. Proven here by setting a
    capacity of 1 (the smallest burst that would deny a second same-bucket
    request within a second of the first) and hammering both exempt routes
    well past it -- every response must still be 200."""
    settings.RATE_LIMIT_CAPACITY = 1
    settings.RATE_LIMIT_REFILL_PER_SECOND = 0.0001  # effectively no refill within this test's runtime
    client = APIClient()

    for _ in range(5):
        health_response = client.get("/health")
        readyz_response = client.get("/readyz")
        assert health_response.status_code == 200
        assert readyz_response.status_code == 200
        assert "Retry-After" not in health_response.headers
        assert "Retry-After" not in readyz_response.headers


# ---------------------------------------------------------------------------
# request-id / audit-bind
# ---------------------------------------------------------------------------


def test_request_id_is_bound_and_reflected_when_absent(api_client: APIClient) -> None:
    response = api_client.get("/health")

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert _UUID_RE.match(request_id), f"expected a minted uuid4, got {request_id!r}"


def test_inbound_request_id_is_reflected_when_shape_valid(api_client: APIClient) -> None:
    response = api_client.get("/health", HTTP_X_REQUEST_ID="trace-abc123.def:456")

    assert response.headers["X-Request-ID"] == "trace-abc123.def:456"


def test_malformed_inbound_request_id_is_replaced_not_reflected(api_client: APIClient) -> None:
    """A request id containing whitespace/control characters (here, an
    embedded newline) doesn't match `_SAFE_REQUEST_ID_RE` -- treated as
    absent, a fresh uuid4 is minted instead of reflecting the malformed
    value back onto the response header or into every audit_event() call
    for this request (core/security/audit_logging/middleware.py's own
    module docstring)."""
    response = api_client.get("/health", HTTP_X_REQUEST_ID="bad\nvalue\r\nwith-crlf")

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert _UUID_RE.match(request_id)
    assert "bad" not in request_id


def test_oversize_inbound_request_id_is_replaced_not_reflected(api_client: APIClient) -> None:
    too_long = "a" * 129  # _SAFE_REQUEST_ID_RE caps at 128 chars

    response = api_client.get("/health", HTTP_X_REQUEST_ID=too_long)

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert _UUID_RE.match(request_id)


# ---------------------------------------------------------------------------
# JSONRenderer-only (references/backend/drf.md's "Browsable API")
# ---------------------------------------------------------------------------


def test_items_endpoint_is_json_only_no_browsable_api(api_client: APIClient) -> None:
    response = api_client.get("/items")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert b"<html" not in response.content.lower()


# ---------------------------------------------------------------------------
# #48 (L2) -- CONN_HEALTH_CHECKS=True (persistent-connection liveness check)
# ---------------------------------------------------------------------------


def test_conn_health_checks_enabled_in_the_real_settings_module() -> None:
    """`config/settings.py`'s `DATABASES` block sets `conn_health_checks=
    True` on `dj_database_url.config(...)` — the cheap mitigation for
    intermittent "connection already closed" errors under
    `CONN_MAX_AGE=600` persistent connections combined with the async-ORM
    thread-sensitive-executor bridge (see that module's own comment, and
    the README's "Database & migrations" -> "Operational note" section).

    Imports `config.settings` directly (NOT `config.settings_test`, this
    test run's actual `DJANGO_SETTINGS_MODULE`) because `settings_test.py`
    overrides `DATABASES` wholesale with a plain sqlite3 dict AFTER `from
    config.settings import *` (see that module's own docstring) -- so
    `django.conf.settings.DATABASES` as observed through the normal Django
    settings object would never show this key during a hermetic test run,
    even though `config/settings.py` itself does set it. `config.settings`
    is already imported as a real module by the time any Django test runs
    (transitively, via `settings_test.py`'s own `import *`), so this is
    inspecting the same already-loaded module object, not re-executing it
    or fighting Django's one-settings-module-per-process constraint."""
    import config.settings as real_settings

    assert real_settings.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True
