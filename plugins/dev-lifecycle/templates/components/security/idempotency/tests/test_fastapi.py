"""Tests for idempotency's fastapi.py middleware against a real FastAPI app
+ TestClient."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def _build_app(fastapi_mod, store):
    app = FastAPI()
    fastapi_mod.add_idempotency(app, store=store)
    counter: list[int] = []

    @app.post("/orders")
    async def create_order(request: Request):
        counter.append(1)
        body = await request.body()
        return {"received": len(body), "call_count": len(counter)}

    return app, counter


def test_no_header_passes_through_untouched(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    r1 = client.post("/orders", json={"amount": 1})
    r2 = client.post("/orders", json={"amount": 1})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # both executed -- no key, no dedup


def test_replay_returns_cached_response_without_rerunning_handler(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = {"Idempotency-Key": "order-abc-123"}
    first = client.post("/orders", json={"amount": 1}, headers=headers)
    second = client.post("/orders", json={"amount": 1}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(counter) == 1  # handler ran exactly once -- second was a replay


def test_conflict_returns_409_for_same_key_different_body(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = {"Idempotency-Key": "order-abc-123"}
    first = client.post("/orders", json={"amount": 1}, headers=headers)
    second = client.post("/orders", json={"amount": 999}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(counter) == 1  # the conflicting request never reached the handler


def test_invalid_key_returns_400(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    response = client.post(
        "/orders", json={"amount": 1}, headers={"Idempotency-Key": "bad key with spaces"}
    )
    assert response.status_code == 400
    assert len(counter) == 0


def test_different_keys_do_not_collide(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    r1 = client.post("/orders", json={"amount": 1}, headers={"Idempotency-Key": "key-a"})
    r2 = client.post("/orders", json={"amount": 1}, headers={"Idempotency-Key": "key-b"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # distinct keys, both executed


def test_server_error_is_not_cached_and_retry_can_still_succeed(fastapi_mod, store):
    app = FastAPI()
    fastapi_mod.add_idempotency(app, store=store)
    attempts: list[int] = []

    @app.post("/flaky")
    async def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            return JSONResponse({"detail": "boom"}, status_code=500)
        return {"ok": True}

    client = TestClient(app)
    headers = {"Idempotency-Key": "flaky-key"}
    first = client.post("/flaky", headers=headers)
    second = client.post("/flaky", headers=headers)

    assert first.status_code == 500
    assert second.status_code == 200  # NOT a replay of the 500 -- retry actually ran
    assert len(attempts) == 2


def test_failure_response_never_leaks_the_key_value(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = {"Idempotency-Key": "order-abc-123"}
    client.post("/orders", json={"amount": 1}, headers=headers)
    response = client.post("/orders", json={"amount": 999}, headers=headers)

    assert "order-abc-123" not in response.text


def test_conflict_is_logged_by_type_only(fastapi_mod, store, caplog):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = {"Idempotency-Key": "order-abc-123"}
    client.post("/orders", json={"amount": 1}, headers=headers)
    with caplog.at_level(logging.WARNING):
        client.post("/orders", json={"amount": 999}, headers=headers)
    assert "IdempotencyConflictError" in caplog.text
    assert "order-abc-123" not in caplog.text
