"""Tests for idempotency's django.py MIDDLEWARE class, exercised via
django.test.RequestFactory."""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory


def _make_middleware(django_mod, store, *, counter):
    def get_response(request):
        counter.append(1)
        body = request.body
        return JsonResponse({"received": len(body), "call_count": len(counter)})

    return django_mod.IdempotencyMiddleware(get_response, store=store)


def test_no_header_passes_through_untouched(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    r1 = middleware(factory.post("/orders", data=b"{}", content_type="application/json"))
    r2 = middleware(factory.post("/orders", data=b"{}", content_type="application/json"))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(counter) == 2  # both executed -- no key, no dedup


def test_replay_returns_cached_response_without_rerunning_handler(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = {"HTTP_IDEMPOTENCY_KEY": "order-abc-123"}

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
    headers = {"HTTP_IDEMPOTENCY_KEY": "order-abc-123"}

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
        )
    )
    assert response.status_code == 400
    assert len(counter) == 0


def test_different_keys_do_not_collide(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()

    r1 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", HTTP_IDEMPOTENCY_KEY="key-a")
    )
    r2 = middleware(
        factory.post("/orders", data=b"{}", content_type="application/json", HTTP_IDEMPOTENCY_KEY="key-b")
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

    middleware = django_mod.IdempotencyMiddleware(get_response, store=store)
    factory = RequestFactory()
    headers = {"HTTP_IDEMPOTENCY_KEY": "flaky-key"}

    first = middleware(factory.post("/flaky", data=b"{}", content_type="application/json", **headers))
    second = middleware(factory.post("/flaky", data=b"{}", content_type="application/json", **headers))

    assert first.status_code == 500
    assert second.status_code == 200  # NOT a replay of the 500 -- retry actually ran
    assert len(attempts) == 2


def test_failure_response_never_leaks_the_key_value(django_mod, store):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = {"HTTP_IDEMPOTENCY_KEY": "order-abc-123"}

    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **headers))
    response = middleware(
        factory.post("/orders", data=b'{"amount": 999}', content_type="application/json", **headers)
    )
    assert b"order-abc-123" not in response.content


def test_conflict_is_logged_by_type_only(django_mod, store, caplog):
    counter: list[int] = []
    middleware = _make_middleware(django_mod, store, counter=counter)
    factory = RequestFactory()
    headers = {"HTTP_IDEMPOTENCY_KEY": "order-abc-123"}

    middleware(factory.post("/orders", data=b'{"amount": 1}', content_type="application/json", **headers))
    with caplog.at_level(logging.WARNING):
        middleware(
            factory.post("/orders", data=b'{"amount": 999}', content_type="application/json", **headers)
        )
    assert "IdempotencyConflictError" in caplog.text
    assert "order-abc-123" not in caplog.text
