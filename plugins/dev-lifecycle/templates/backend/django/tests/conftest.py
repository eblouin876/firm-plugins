"""Shared pytest-django fixtures for this block's test suite. `pytest.ini_options`
(pyproject.toml) points `DJANGO_SETTINGS_MODULE` at `config.settings_test` —
the hermetic sqlite settings — so every test here runs with no real Postgres
server reachable, mirroring backend/fastapi's own hermetic aiosqlite test
posture (tests/conftest.py there)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


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
