"""Tests for cors-lockdown's django.py: a config emitter, not a middleware,
so these tests check translation shape, not request/response behavior
(django-cors-headers itself owns the request-handling behavior)."""

from __future__ import annotations


def test_cors_settings_matches_core_translation(django_mod, core_mod):
    policy = core_mod.CORSPolicy(
        allow_origins=("https://app.example.com",),
        allow_credentials=True,
        allow_methods=("GET", "POST"),
        allow_headers=("Content-Type",),
        max_age=300,
    )
    assert django_mod.cors_settings(policy) == policy.to_django_cors_headers_settings()


def test_cors_settings_rejects_nothing_extra(django_mod, core_mod):
    policy = core_mod.CORSPolicy(allow_origins=("https://app.example.com",))
    settings = django_mod.cors_settings(policy)
    assert set(settings) == {
        "CORS_ALLOWED_ORIGINS",
        "CORS_ALLOW_CREDENTIALS",
        "CORS_ALLOW_METHODS",
        "CORS_ALLOW_HEADERS",
        "CORS_PREFLIGHT_MAX_AGE",
    }


def test_middleware_classpath_and_app_constants(django_mod):
    assert django_mod.CORS_MIDDLEWARE_CLASSPATH == "corsheaders.middleware.CorsMiddleware"
    assert django_mod.REQUIRED_INSTALLED_APP == "corsheaders"
