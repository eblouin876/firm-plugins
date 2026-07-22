"""Tests for cors-lockdown's _core.py: the construction-time guardrails and
the two settings-translation functions."""

from __future__ import annotations

import pytest


def test_wildcard_origin_alone_is_rejected(core_mod):
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=("*",), allow_credentials=False)


def test_wildcard_origin_with_credentials_is_rejected(core_mod):
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=("*",), allow_credentials=True)


def test_empty_origins_list_is_rejected(core_mod):
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=())


def test_blank_origin_entry_with_credentials_is_rejected(core_mod):
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=("https://app.example.com", ""), allow_credentials=True)


def test_blank_origin_entry_without_credentials_is_also_rejected(core_mod):
    """NIT-10: blank origins are rejected unconditionally, not only under
    allow_credentials=True."""
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=("https://app.example.com", ""), allow_credentials=False)


def test_whitespace_only_origin_entry_is_rejected(core_mod):
    with pytest.raises(core_mod.InsecureCORSPolicyError):
        core_mod.CORSPolicy(allow_origins=("https://app.example.com", "   "), allow_credentials=False)


def test_valid_explicit_allowlist_constructs(core_mod):
    policy = core_mod.CORSPolicy(
        allow_origins=("https://app.example.com",), allow_credentials=True
    )
    assert policy.allow_origins == ("https://app.example.com",)
    assert policy.allow_credentials is True


def test_defaults_are_minimal(core_mod):
    policy = core_mod.CORSPolicy(allow_origins=("https://app.example.com",))
    assert policy.allow_credentials is False
    assert set(policy.allow_methods) <= {"GET", "HEAD", "POST"}
    assert policy.max_age == 600


def test_to_starlette_kwargs_shape(core_mod):
    policy = core_mod.CORSPolicy(
        allow_origins=("https://app.example.com",),
        allow_credentials=True,
        allow_methods=("GET", "POST"),
        allow_headers=("Content-Type",),
        max_age=300,
    )
    kwargs = policy.to_starlette_kwargs()
    assert kwargs == {
        "allow_origins": ["https://app.example.com"],
        "allow_credentials": True,
        "allow_methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"],
        "max_age": 300,
    }


def test_to_django_cors_headers_settings_shape(core_mod):
    policy = core_mod.CORSPolicy(
        allow_origins=("https://app.example.com",),
        allow_credentials=True,
        allow_methods=("GET", "POST"),
        allow_headers=("Content-Type", "Authorization"),
        max_age=300,
    )
    settings = policy.to_django_cors_headers_settings()
    assert settings == {
        "CORS_ALLOWED_ORIGINS": ["https://app.example.com"],
        "CORS_ALLOW_CREDENTIALS": True,
        "CORS_ALLOW_METHODS": ["GET", "POST"],
        "CORS_ALLOW_HEADERS": ["content-type", "authorization"],
        "CORS_PREFLIGHT_MAX_AGE": 300,
    }


def test_policy_is_frozen(core_mod):
    policy = core_mod.CORSPolicy(allow_origins=("https://app.example.com",))
    with pytest.raises(Exception):
        policy.allow_origins = ("https://evil.example.com",)
