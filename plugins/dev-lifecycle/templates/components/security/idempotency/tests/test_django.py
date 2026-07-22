"""Tests for idempotency's django.py MIDDLEWARE class, exercised via
django.test.RequestFactory."""

from __future__ import annotations

import json
import logging

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory

# Every test request carries a custom HTTP_X_PRINCIPAL META key (a stand-in
# for whatever request.user a real AuthenticationMiddleware would have
# already populated by the time this middleware runs) so tests can drive
# different principals without wiring real Django auth.
_PRINCIPAL_META_KEY = "HTTP_X_PRINCIPAL"


def _principal_getter(request):
    return request.META.get(_PRINCIPAL_META_KEY) or None


def _make_middleware(django_mod, store, *, counter, principal_getter=_principal_getter):
    def get_response(request):
        counter.append(1)
        body = request.body
        return JsonResponse({"received": len(body), "call_count": len(counter)})

    return django_mod.IdempotencyMiddleware(get_response, store=store, principal_getter=principal_getter)


def _headers(principal: str, key: str) -> dict[str, str]:
    return {_PRINCIPAL_META_KEY: principal, "HTTP_IDEMPOTENCY_KEY": key}


def test_no_header_passes_through_untouched(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    r1 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", **{_PRINCIPAL_META_KEY: "alice"})
    )
    r2 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", **{_PRINCIPAL_META_KEY: "alice"})
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # both executed -- no key, no dedup


def test_replay_returns_cached_response_without_rerunning_handler(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = _headers("alice", "order-abc-123")

    first = middleware(factory.post("/orders", data=b"{}", content_type="application/json", **headers))
    second = middleware(factory.post("/orders", data=b"{}", content_type="application/json", **headers))

    assert first.status_code == 200
    assert second.status_code == 200
    assert json.loads(first.content) == json.loads(second.content)
    assert len(counter) == 1  # handler ran exactly once -- second was a replay


def test_conflict_returns_409_for_same_key_different_body(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = _headers("alice", "order-abc-123")

    first = middleware(
        factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **headers)
    )
    second = middleware(
        factory.post("/orders", data=b'{"amount": 999}', content_type="application/json", **headers)
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(counter) == 1  # the conflicting request never reached the handler


def test_invalid_key_returns_400(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    response = middleware(
        factory.post(
            "/orders",
            data=b"{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="bad key with spaces",
            **{_PRINCIPAL_META_KEY: "alice"},
        )
    )
    assert response.status_code == 400
    assert len(counter) == 0


def test_different_keys_do_not_collide(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    r1 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", **_headers("alice", "key-a"))
    )
    r2 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", **_headers("alice", "key-b"))
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # distinct keys, both executed


def test_server_error_is_not_cached_and_retry_can_still_succeed(django_mod, store):
    attempts: list[int] = []

    def get_response(request):
        attempts.append(1)
        if len(attempts) == 1:
            return HttpResponse("boom", status=500)
        return HttpResponse("ok", status=200)

    middleware = django_mod.IdempotencyMiddleware(get_response, store=store, principal_getter=_principal_getter)
    factory = RequestFactory()
    headers = _headers("alice", "flaky-key")

    first = middleware(factory.post("/flaky", data=b"{}", content_type="application/json", **headers))
    second = middleware(factory.post("/flaky", data=b"{}", content_type="application/json", **headers))

    assert first.status_code == 500
    assert second.status_code == 200  # NOT a replay of the 500 -- retry actually ran
    assert len(attempts) == 2


def test_failure_response_never_leaks_the_key_value(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = _headers("alice", "order-abc-123")

    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **headers))
    response = middleware(
        factory.post("/orders", data=b'{"amount": 999}', content_type="application/json", **headers)
    )
    assert b"order-abc-123" not in response.content


def test_conflict_is_logged_by_type_only(django_mod, store, caplog):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = _headers("alice", "order-abc-123")

    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **headers))
    with caplog.at_level(logging.WARNING):
        middleware(
            factory.post("/orders", data=b'{"amount": 999}', content_type="application/json", **headers)
        )
    assert "IdempotencyConflictError" in caplog.text
    assert "order-abc-123" not in caplog.text


# --- BLOCKER-1: principal-scoped storage key, no cross-principal replay -----


def test_same_key_same_body_two_principals_both_execute(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    alice_response = middleware(
        factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **_headers("alice", "shared-key"))
    )
    bob_response = middleware(
        factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **_headers("bob", "shared-key"))
    )

    assert alice_response.status_code == 200
    assert bob_response.status_code == 200
    assert len(counter) == 2  # both executed -- NOT a replay across principals


def test_alice_replay_still_works_despite_bobs_same_key(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    alice_headers = _headers("alice", "shared-key")
    bob_headers = _headers("bob", "shared-key")

    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **alice_headers))
    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **bob_headers))
    alice_replay = middleware(
        factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **alice_headers)
    )

    assert alice_replay.status_code == 200
    assert len(counter) == 2  # alice's second request was a replay, not a third execution


def test_anonymous_request_is_passthrough_not_shared_namespace(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    # No X-Principal META key -- anonymous under the default policy.
    headers = {"HTTP_IDEMPOTENCY_KEY": "anon-shared-key"}

    first = middleware(factory.post("/orders", data=b"{}", content_type="application/json", **headers))
    second = middleware(factory.post("/orders", data=b"{}", content_type="application/json", **headers))

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(counter) == 2  # no dedup for anonymous requests under the default policy


def test_missing_principal_getter_raises_improperly_configured(django_mod, store):
    def get_response(request):
        return HttpResponse("ok")

    with pytest.raises(ImproperlyConfigured):
        django_mod.IdempotencyMiddleware(get_response, store=store)  # no principal_getter, no setting


def test_default_principal_getter_uses_authenticated_user_pk(django_mod):
    class _FakeUser:
        pk = 42
        is_authenticated = True

    class _FakeRequest:
        user = _FakeUser()

    assert django_mod.default_principal_getter(_FakeRequest()) == "42"


def test_default_principal_getter_returns_none_for_anonymous(django_mod):
    class _AnonymousUser:
        is_authenticated = False

    class _FakeRequest:
        user = _AnonymousUser()

    assert django_mod.default_principal_getter(_FakeRequest()) is None


# --- HIGH-2: sensitive headers are never replayed ---------------------------


def test_set_cookie_is_never_replayed(django_mod, store):
    def get_response(request):
        response = HttpResponse('{"ok": true}', content_type="application/json")
        response["Set-Cookie"] = "session=abc123; HttpOnly"
        return response

    middleware = django_mod.IdempotencyMiddleware(get_response, store=store, principal_getter=_principal_getter)
    factory = RequestFactory()
    headers = _headers("alice", "login-key")

    first = middleware(factory.post("/login", data=b"{}", content_type="application/json", **headers))
    second = middleware(factory.post("/login", data=b"{}", content_type="application/json", **headers))

    assert first["Set-Cookie"] == "session=abc123; HttpOnly"
    assert "Set-Cookie" not in second
