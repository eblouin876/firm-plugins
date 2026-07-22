"""Tests for cors-lockdown's fastapi.py against a real Starlette app +
TestClient, focused on preflight shape."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _build_app(fastapi_mod, core_mod):
    async def homepage(request):
        return PlainTextResponse("hello")

    app = Starlette(routes=[Route("/", homepage)])
    policy = core_mod.CORSPolicy(
        allow_origins=("https://app.example.com",),
        allow_credentials=True,
        allow_methods=("GET", "POST"),
        allow_headers=("Content-Type", "Authorization"),
        max_age=300,
    )
    fastapi_mod.add_cors(app, policy)
    return app


def test_preflight_from_allowed_origin(fastapi_mod, core_mod):
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.options(
        "/",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-max-age"] == "300"


def test_preflight_from_disallowed_origin_omits_allow_origin(fastapi_mod, core_mod):
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.options(
        "/",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Starlette's CORSMiddleware still returns 200 to the preflight itself,
    # but omits the Allow-Origin header for a non-allowlisted origin -- the
    # browser is what actually enforces the block based on that absence.
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_allowed_origin_gets_header(fastapi_mod, core_mod):
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.get("/", headers={"Origin": "https://app.example.com"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
