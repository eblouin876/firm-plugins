"""Tests for security-headers' fastapi.py (pure-ASGI middleware) against a
real Starlette app + TestClient."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _build_app(fastapi_mod, *, existing_header: bool = False):
    async def homepage(request):
        headers = {"X-Frame-Options": "SAMEORIGIN"} if existing_header else {}
        return PlainTextResponse("hello", headers=headers)

    app = Starlette(routes=[Route("/", homepage)])
    fastapi_mod.add_security_headers(app)
    return app


def test_middleware_sets_headers_on_response(fastapi_mod):
    client = TestClient(_build_app(fastapi_mod), base_url="https://testserver")
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "content-security-policy" in response.headers
    assert "permissions-policy" in response.headers


def test_middleware_sets_hsts_over_https(fastapi_mod):
    client = TestClient(_build_app(fastapi_mod), base_url="https://testserver")
    response = client.get("/")
    assert "strict-transport-security" in response.headers


def test_middleware_omits_hsts_over_plain_http(fastapi_mod):
    client = TestClient(_build_app(fastapi_mod), base_url="http://testserver")
    response = client.get("/")
    assert "strict-transport-security" not in response.headers


def test_middleware_overwrites_a_downstream_handlers_own_header(fastapi_mod):
    """A route handler set X-Frame-Options itself; the middleware's policy
    (DENY) must win, not the handler's own value -- 'component wins' per
    the README's headers-interplay judgment call."""
    client = TestClient(_build_app(fastapi_mod, existing_header=True), base_url="https://testserver")
    response = client.get("/")
    assert response.headers["x-frame-options"] == "DENY"


def test_middleware_does_not_duplicate_headers(fastapi_mod):
    client = TestClient(_build_app(fastapi_mod, existing_header=True), base_url="https://testserver")
    raw = client.get("/")
    # httpx's headers object folds duplicates transparently on read, so
    # assert directly on the raw header list length instead.
    frame_option_lines = [v for k, v in raw.headers.raw if k.decode().lower() == "x-frame-options"]
    assert len(frame_option_lines) == 1
