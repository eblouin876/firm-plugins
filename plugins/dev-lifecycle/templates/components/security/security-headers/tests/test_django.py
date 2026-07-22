"""Tests for security-headers' django.py MIDDLEWARE class, exercised
directly against Django's RequestFactory (no urlconf/app needed for a
single middleware unit test)."""

from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory


def _get_response_with_existing_header(request):
    response = HttpResponse("hello")
    response["X-Frame-Options"] = "SAMEORIGIN"  # simulates Django's own SecurityMiddleware
    return response


def _get_response_plain(request):
    return HttpResponse("hello")


def test_middleware_sets_headers(django_mod):
    factory = RequestFactory()
    request = factory.get("/", secure=True)
    middleware = django_mod.SecurityHeadersMiddleware(_get_response_plain)
    response = middleware(request)
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response
    assert "Permissions-Policy" in response


def test_middleware_sets_hsts_over_https(django_mod):
    factory = RequestFactory()
    request = factory.get("/", secure=True)
    middleware = django_mod.SecurityHeadersMiddleware(_get_response_plain)
    response = middleware(request)
    assert "Strict-Transport-Security" in response


def test_middleware_omits_hsts_over_plain_http(django_mod):
    factory = RequestFactory()
    request = factory.get("/", secure=False)
    middleware = django_mod.SecurityHeadersMiddleware(_get_response_plain)
    response = middleware(request)
    assert "Strict-Transport-Security" not in response


def test_middleware_overwrites_prior_middlewares_header(django_mod):
    """Django's own SecurityMiddleware (or another earlier-run middleware)
    already set X-Frame-Options; this component's middleware must have the
    final say per the README's headers-interplay judgment call."""
    factory = RequestFactory()
    request = factory.get("/", secure=True)
    middleware = django_mod.SecurityHeadersMiddleware(_get_response_with_existing_header)
    response = middleware(request)
    assert response["X-Frame-Options"] == "DENY"
