"""Tests for webhook-signature's django.py decorator, exercised via
django.test.RequestFactory."""

from __future__ import annotations

import logging
import time

from django.http import HttpResponse
from django.test import RequestFactory

FAKE_SECRET = "whsec_django-fake-not-real"


def _sign(core_mod, timestamp: int, body: bytes) -> str:
    sig = core_mod.compute_signature(FAKE_SECRET, timestamp, body)
    return f"t={timestamp},v1={sig}"


def _make_view(django_mod, *, tolerance_s: int = 300):
    calls = []

    @django_mod.require_webhook_signature(lambda: FAKE_SECRET, tolerance_s=tolerance_s)
    def webhook(request):
        calls.append(request.body)
        return HttpResponse("ok")

    return webhook, calls


def test_valid_signature_calls_the_view(django_mod, core_mod):
    view, calls = _make_view(django_mod)
    now = int(time.time())
    body = b'{"event": "ok"}'
    header = _sign(core_mod, now, body)
    request = RequestFactory().post(
        "/webhook", data=body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header
    )
    response = view(request)
    assert response.status_code == 200
    assert calls == [body]


def test_tampered_body_returns_400_and_skips_the_view(django_mod, core_mod):
    view, calls = _make_view(django_mod)
    now = int(time.time())
    header = _sign(core_mod, now, b'{"amount": 1}')
    request = RequestFactory().post(
        "/webhook",
        data=b'{"amount": 999}',
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )
    response = view(request)
    assert response.status_code == 400
    assert calls == []  # the view body must never run on a failed verification


def test_expired_timestamp_returns_400(django_mod, core_mod):
    view, _ = _make_view(django_mod, tolerance_s=300)
    stale = int(time.time()) - 10_000
    body = b"{}"
    header = _sign(core_mod, stale, body)
    request = RequestFactory().post(
        "/webhook", data=body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header
    )
    response = view(request)
    assert response.status_code == 400


def test_missing_header_returns_400(django_mod, core_mod):
    view, _ = _make_view(django_mod)
    request = RequestFactory().post("/webhook", data=b"{}", content_type="application/json")
    response = view(request)
    assert response.status_code == 400


def test_failure_is_logged_by_type_only(django_mod, core_mod, caplog):
    view, _ = _make_view(django_mod)
    now = int(time.time())
    header = _sign(core_mod, now, b"original-body")
    request = RequestFactory().post(
        "/webhook", data=b"tampered-body", content_type="application/json", HTTP_STRIPE_SIGNATURE=header
    )
    with caplog.at_level(logging.WARNING):
        view(request)
    assert "SignatureMismatchError" in caplog.text
    assert header not in caplog.text
    assert FAKE_SECRET not in caplog.text
