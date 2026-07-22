"""Tests for webhook-signature's fastapi.py dependency against a real
FastAPI app + TestClient."""

from __future__ import annotations

import logging
import time

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

FAKE_SECRET = "whsec_fastapi-fake-not-real"


def _build_app(fastapi_mod, core_mod, *, tolerance_s: int = 300):
    app = FastAPI()
    verifier = fastapi_mod.make_webhook_verification_dependency(
        lambda: FAKE_SECRET, tolerance_s=tolerance_s
    )

    @app.post("/webhook")
    async def webhook(raw_body: bytes = Depends(verifier)):
        return {"received": len(raw_body)}

    return app


def _sign(core_mod, timestamp: int, body: bytes) -> str:
    sig = core_mod.compute_signature(FAKE_SECRET, timestamp, body)
    return f"t={timestamp},v1={sig}"


def test_valid_signature_returns_200(fastapi_mod, core_mod):
    now = int(time.time())
    body = b'{"event": "ok"}'
    header = _sign(core_mod, now, body)
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.post("/webhook", content=body, headers={"stripe-signature": header})
    assert response.status_code == 200


def test_tampered_body_returns_400(fastapi_mod, core_mod):
    now = int(time.time())
    header = _sign(core_mod, now, b'{"amount": 1}')
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.post(
        "/webhook", content=b'{"amount": 999}', headers={"stripe-signature": header}
    )
    assert response.status_code == 400


def test_expired_timestamp_returns_400(fastapi_mod, core_mod):
    stale = int(time.time()) - 10_000
    body = b"{}"
    header = _sign(core_mod, stale, body)
    client = TestClient(_build_app(fastapi_mod, core_mod, tolerance_s=300))
    response = client.post("/webhook", content=body, headers={"stripe-signature": header})
    assert response.status_code == 400


def test_missing_header_returns_400(fastapi_mod, core_mod):
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.post("/webhook", content=b"{}")
    assert response.status_code == 400


def test_failure_response_never_leaks_the_signature(fastapi_mod, core_mod):
    now = int(time.time())
    header = _sign(core_mod, now, b"original-body")
    client = TestClient(_build_app(fastapi_mod, core_mod))
    response = client.post("/webhook", content=b"tampered-body", headers={"stripe-signature": header})
    assert header not in response.text
    assert FAKE_SECRET not in response.text


def test_failure_is_logged_by_type_only(fastapi_mod, core_mod, caplog):
    now = int(time.time())
    header = _sign(core_mod, now, b"original-body")
    client = TestClient(_build_app(fastapi_mod, core_mod))
    with caplog.at_level(logging.WARNING):
        client.post("/webhook", content=b"tampered-body", headers={"stripe-signature": header})
    assert "SignatureMismatchError" in caplog.text
    assert header not in caplog.text
    assert FAKE_SECRET not in caplog.text
