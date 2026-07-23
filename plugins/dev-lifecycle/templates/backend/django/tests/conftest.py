"""Shared pytest-django fixtures for this block's test suite. `pytest.ini_options`
(pyproject.toml) points `DJANGO_SETTINGS_MODULE` at `config.settings_test` —
the hermetic sqlite settings — so every test here runs with no real Postgres
server reachable, mirroring backend/fastapi's own hermetic aiosqlite test
posture (tests/conftest.py there)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

import core.security.rate_limiting.django as rate_limiting_django


@pytest.fixture(autouse=True)
def _reset_rate_limit_store() -> None:
    """Stage 4 review fix (#27): `core.security.rate_limiting.django.
    RateLimitMiddleware` shares one module-level `_default_store` singleton
    across every request a process handles (that module's own docstring) --
    a real, load-bearing behavior in production (one bucket per client IP,
    not one per request), but a test-isolation hazard here: every test in
    this suite hits the same singleton through the same test-client
    REMOTE_ADDR ('127.0.0.1' by default), so without a reset a bucket
    exhausted by an earlier test's burst could leak a 429 into a LATER,
    unrelated test -- order-dependent flakiness that gets more likely, not
    less, as the suite grows. Autouse + reset-before (not after) so the
    very first test in a run also starts from a clean singleton, and so a
    fixture added later that inspects `_default_store` post-test still sees
    what its own test actually did. `test_security_composition.py`'s
    rate-limit tests no longer need to do this by hand -- this fixture
    covers every test in the suite, not just those two."""
    rate_limiting_django._default_store = None


@pytest.fixture()
def api_client() -> APIClient:
    """Plain DRF test client for the normal (2xx/expected-4xx) paths."""
    return APIClient()


@pytest.fixture()
def crashing_client() -> APIClient:
    """`raise_request_exception=False`: without this, Django's test Client
    re-raises any exception that reaches its own outermost handler instead
    of turning it into a real HTTP response — the same reason backend/
    fastapi's own `crashing_client` fixture (tests/test_error_envelope.py)
    passes `raise_server_exceptions=False` to `TestClient`. Used only by the
    forced-500 conformance test — every exception DRF's own `APIView.
    dispatch()` catches is routed through `core.exceptions.exception_handler`
    regardless of this flag; it only matters for the rare case something
    still escapes that (this fixture is defense-in-depth, not load-bearing
    for the normal error paths)."""
    return APIClient(raise_request_exception=False)
