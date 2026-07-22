"""Tests for security-headers' _core.py: policy defaults, CSP builder, and
Permissions-Policy rendering."""

from __future__ import annotations


def test_default_policy_sets_every_expected_header(core_mod):
    headers = core_mod.DEFAULT_POLICY.build_headers(is_https=True)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in headers
    assert "Permissions-Policy" in headers
    assert "Strict-Transport-Security" in headers


def test_hsts_omitted_on_non_https(core_mod):
    headers = core_mod.DEFAULT_POLICY.build_headers(is_https=False)
    assert "Strict-Transport-Security" not in headers


def test_hsts_value_shape(core_mod):
    headers = core_mod.DEFAULT_POLICY.build_headers(is_https=True)
    hsts = headers["Strict-Transport-Security"]
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" not in hsts  # preload is opt-in, not the default


def test_hsts_preload_opt_in():
    from dataclasses import replace

    import _core

    policy = replace(_core.DEFAULT_POLICY, hsts_preload=True)
    headers = policy.build_headers(is_https=True)
    assert "preload" in headers["Strict-Transport-Security"]


def test_default_csp_is_restrictive(core_mod):
    csp = core_mod.CSPPolicy().build()
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_csp_allow_adds_directive_without_mutating_default(core_mod):
    base = core_mod.CSPPolicy()
    relaxed = base.allow("script-src", "'self'", "https://cdn.example.com")
    assert "script-src 'self' https://cdn.example.com" in relaxed.build()
    # the original policy object is untouched -- .allow() returns a NEW policy
    assert "script-src" not in base.build()


def test_csp_allow_is_additive_not_overriding(core_mod):
    base = core_mod.CSPPolicy().allow("script-src", "'self'")
    relaxed = base.allow("script-src", "https://cdn.example.com")
    rendered = relaxed.build()
    assert "'self'" in rendered
    assert "https://cdn.example.com" in rendered


def test_csp_allow_deduplicates_sources(core_mod):
    policy = core_mod.CSPPolicy().allow("default-src", "'self'")  # already present
    directive_value = policy.directives["default-src"]
    assert directive_value.count("'self'") == 1


def test_permissions_policy_denies_by_default(core_mod):
    headers = core_mod.DEFAULT_POLICY.build_headers(is_https=True)
    pp = headers["Permissions-Policy"]
    assert "camera=()" in pp
    assert "microphone=()" in pp
    assert "geolocation=()" in pp


def test_permissions_policy_can_be_widened():
    from dataclasses import replace

    import _core

    policy = replace(_core.DEFAULT_POLICY, permissions_policy={"camera": ("self",)})
    headers = policy.build_headers(is_https=True)
    assert "camera=(self)" in headers["Permissions-Policy"]


def test_frame_options_configurable():
    from dataclasses import replace

    import _core

    policy = replace(_core.DEFAULT_POLICY, frame_options="SAMEORIGIN")
    headers = policy.build_headers(is_https=True)
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
