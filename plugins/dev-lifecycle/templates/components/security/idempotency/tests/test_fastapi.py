"""Tests for idempotency's fastapi.py middleware against a real FastAPI app
+ TestClient."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

# Every test app resolves the principal from a custom `X-Principal` header
# (a stand-in for whatever an app's real auth middleware would populate on
# request.state -- e.g. request.state.user_id) so tests can drive different
# principals without wiring a real auth stack.
_PRINCIPAL_HEADER = "X-Principal"


def _principal_getter(request: Request) -> str | None:
    return request.headers.get(_PRINCIPAL_HEADER) or None


def _build_app(fastapi_mod, store, *, principal_getter=_principal_getter):
    app = FastAPI()
    fastapi_mod.add_idempotency(app, store=store, principal_getter=principal_getter)
    counter: list[int] = []

    @app.post("/orders")
    async def create_order(request: Request):
        counter.append(1)
        body = await request.body()
        return {"received": len(body), "call_count": len(counter)}

    return app, counter


def _headers(principal: str, key: str) -> dict[str, str]:
    return {_PRINCIPAL_HEADER: principal, "Idempotency-Key": key}


def test_no_header_passes_through_untouched(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    r1 = client.post("/orders", json={"amount": 1}, headers={_PRINCIPAL_HEADER: "alice"})
    r2 = client.post("/orders", json={"amount": 1}, headers={_PRINCIPAL_HEADER: "alice"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # both executed -- no key, no dedup


def test_replay_returns_cached_response_without_rerunning_handler(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = _headers("alice", "order-abc-123")
    first = client.post("/orders", json={"amount": 1}, headers=headers)
    second = client.post("/orders", json={"amount": 1}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(counter) == 1  # handler ran exactly once -- second was a replay


def test_conflict_returns_409_for_same_key_different_body(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = _headers("alice", "order-abc-123")
    first = client.post("/orders", json={"amount": 1}, headers=headers)
    second = client.post("/orders", json={"amount": 999}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(counter) == 1  # the conflicting request never reached the handler


def test_invalid_key_returns_400(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    response = client.post(
        "/orders",
        json={"amount": 1},
        headers={_PRINCIPAL_HEADER: "alice", "Idempotency-Key": "bad key with spaces"},
    )
    assert response.status_code == 400
    assert len(counter) == 0


def test_different_keys_do_not_collide(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    r1 = client.post("/orders", json={"amount": 1}, headers=_headers("alice", "key-a"))
    r2 = client.post("/orders", json={"amount": 1}, headers=_headers("alice", "key-b"))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # distinct keys, both executed


def test_server_error_is_not_cached_and_retry_can_still_succeed(fastapi_mod, store):
    app = FastAPI()
    fastapi_mod.add_idempotency(app, store=store, principal_getter=_principal_getter)
    attempts: list[int] = []

    @app.post("/flaky")
    async def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            return JSONResponse({"detail": "boom"}, status_code=500)
        return {"ok": True}

    client = TestClient(app)
    headers = _headers("alice", "flaky-key")
    first = client.post("/flaky", headers=headers)
    second = client.post("/flaky", headers=headers)

    assert first.status_code == 500
    assert second.status_code == 200  # NOT a replay of the 500 -- retry actually ran
    assert len(attempts) == 2


def test_failure_response_never_leaks_the_key_value(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = _headers("alice", "order-abc-123")
    client.post("/orders", json={"amount": 1}, headers=headers)
    response = client.post("/orders", json={"amount": 999}, headers=headers)

    assert "order-abc-123" not in response.text


def test_conflict_is_logged_by_type_only(fastapi_mod, store, caplog):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = _headers("alice", "order-abc-123")
    client.post("/orders", json={"amount": 1}, headers=headers)
    with caplog.at_level(logging.WARNING):
        client.post("/orders", json={"amount": 999}, headers=headers)
    assert "IdempotencyConflictError" in caplog.text
    assert "order-abc-123" not in caplog.text


# --- BLOCKER-1: principal-scoped storage key, no cross-principal replay -----


def test_same_key_same_body_two_principals_both_execute(fastapi_mod, store):
    """The load-bearing regression test for the cross-user replay fix:
    two DIFFERENT principals using the identical Idempotency-Key (and even
    the identical body) must each get their own execution -- alice must
    never receive bob's stored response, or vice versa."""
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    same_key_headers_alice = _headers("alice", "shared-key")
    same_key_headers_bob = _headers("bob", "shared-key")

    alice_response = client.post("/orders", json={"amount": 1}, headers=same_key_headers_alice)
    bob_response = client.post("/orders", json={"amount": 1}, headers=same_key_headers_bob)

    assert alice_response.status_code == 200
    assert bob_response.status_code == 200
    assert len(counter) == 2  # both executed -- NOT a replay across principals
    assert alice_response.json()["call_count"] != bob_response.json()["call_count"]


def test_alice_replay_still_works_despite_bobs_same_key(fastapi_mod, store):
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    alice_headers = _headers("alice", "shared-key")
    bob_headers = _headers("bob", "shared-key")

    client.post("/orders", json={"amount": 1}, headers=alice_headers)
    client.post("/orders", json={"amount": 1}, headers=bob_headers)
    alice_replay = client.post("/orders", json={"amount": 1}, headers=alice_headers)

    assert alice_replay.status_code == 200
    assert len(counter) == 2  # alice's second request was a replay, not a third execution


def test_anonymous_request_is_passthrough_not_shared_namespace(fastapi_mod, store):
    """Default anonymous policy: principal_getter returning None means full
    passthrough (as if there were no Idempotency-Key header) -- never a
    shared anonymous namespace that would let two different anonymous
    callers collide with each other."""
    app, counter = _build_app(fastapi_mod, store)
    client = TestClient(app)
    headers = {"Idempotency-Key": "anon-shared-key"}  # no X-Principal header

    first = client.post("/orders", json={"amount": 1}, headers=headers)
    second = client.post("/orders", json={"amount": 1}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(counter) == 2  # no dedup for anonymous requests under the default policy


def test_principal_getter_is_required(fastapi_mod, store):
    import pytest

    with pytest.raises(TypeError):
        fastapi_mod.add_idempotency(FastAPI(), store=store)  # missing principal_getter


# --- HIGH-2: sensitive headers are never replayed ---------------------------


def test_set_cookie_is_never_replayed(fastapi_mod, store):
    from starlette.responses import Response

    app = FastAPI()
    fastapi_mod.add_idempotency(app, store=store, principal_getter=_principal_getter)

    @app.post("/login")
    async def login():
        return Response(content='{"ok": true}', media_type="application/json", headers={"Set-Cookie": "session=abc123; HttpOnly"})

    client = TestClient(app)
    headers = _headers("alice", "login-key")
    first = client.post("/login", headers=headers)
    second = client.post("/login", headers=headers)

    assert first.headers.get("set-cookie") == "session=abc123; HttpOnly"  # first response: real
    assert "set-cookie" not in second.headers  # replay: stripped, never re-sent
