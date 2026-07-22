"""Tests for rate-limiting's django.py MIDDLEWARE class, exercised via
django.test.RequestFactory."""

from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory


def _get_response(request):
    return HttpResponse("ok")


def test_middleware_allows_then_429s_with_retry_after(django_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    middleware = django_mod.RateLimitMiddleware(
        _get_response, store=store, capacity=2, refill_per_second=0.001
    )
    factory = RequestFactory()
    request = factory.get("/", REMOTE_ADDR="203.0.113.5")

    assert middleware(request).status_code == 200
    assert middleware(request).status_code == 200
    third = middleware(request)
    assert third.status_code == 429
    assert "Retry-After" in third
    assert int(third["Retry-After"]) >= 0


def test_middleware_per_key_isolation_by_remote_addr(django_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    middleware = django_mod.RateLimitMiddleware(
        _get_response, store=store, capacity=1, refill_per_second=0.001
    )
    factory = RequestFactory()

    alice = factory.get("/", REMOTE_ADDR="203.0.113.1")
    bob = factory.get("/", REMOTE_ADDR="203.0.113.2")

    assert middleware(alice).status_code == 200
    assert middleware(alice).status_code == 429  # alice drained her own bucket
    assert middleware(bob).status_code == 200  # bob's bucket is untouched


def test_middleware_ignores_xff_by_default(django_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    middleware = django_mod.RateLimitMiddleware(
        _get_response, store=store, capacity=1, refill_per_second=0.001
    )
    factory = RequestFactory()
    # Two requests from the same REMOTE_ADDR but spoofed, different XFF --
    # without trusted_hops, XFF must be ignored, so both bucket on the same
    # REMOTE_ADDR and the second is denied.
    first = factory.get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="1.2.3.4")
    second = factory.get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="5.6.7.8")

    assert middleware(first).status_code == 200
    assert middleware(second).status_code == 429


def test_middleware_honors_xff_rightmost_when_trusted_hops_set(django_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    middleware = django_mod.RateLimitMiddleware(
        _get_response, store=store, capacity=1, refill_per_second=0.001, trusted_hops=1
    )
    factory = RequestFactory()
    # Same proxy REMOTE_ADDR, different RIGHTMOST (trusted) XFF entries ->
    # isolated buckets keyed on the rightmost entry, not REMOTE_ADDR.
    first = factory.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.9.9.9, 1.2.3.4")
    second = factory.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.9.9.9, 5.6.7.8")

    assert middleware(first).status_code == 200
    assert middleware(second).status_code == 200


def test_middleware_spoofed_leftmost_xff_does_not_bypass_the_limit(django_mod, core_mod):
    """HIGH-3 regression at the middleware level: an attacker varying only
    the client-controlled leftmost XFF entry must still hit the SAME
    bucket (and get rate-limited) when trusted_hops=1, since the rightmost
    (trusted) entry is unchanged."""
    store = core_mod.InMemoryBucketStore()
    middleware = django_mod.RateLimitMiddleware(
        _get_response, store=store, capacity=1, refill_per_second=0.001, trusted_hops=1
    )
    factory = RequestFactory()
    first = factory.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.1.1.1, 5.6.7.8")
    second = factory.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="9.9.9.9, 5.6.7.8")

    assert middleware(first).status_code == 200
    assert middleware(second).status_code == 429  # same rightmost entry -- same bucket, denied


# --- MEDIUM-7: refill_per_second<=0 rejected at construction ---------------


def test_construction_rejects_zero_refill_rate(django_mod, core_mod):
    import pytest

    store = core_mod.InMemoryBucketStore()
    with pytest.raises(ValueError):
        django_mod.RateLimitMiddleware(_get_response, store=store, capacity=1, refill_per_second=0)
