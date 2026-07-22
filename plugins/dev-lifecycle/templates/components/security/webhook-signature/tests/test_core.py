"""Tests for webhook-signature's _core.py: valid/tampered/expired
verification, the Stripe-style header parser, constant-time comparison,
and that a signature/secret value is never logged.

Values used throughout are obviously fake (e.g. "whsec_fake-not-real") --
no real webhook secret ever appears in this file.
"""

from __future__ import annotations

import hmac
import logging

import pytest

FAKE_SECRET = "whsec_fake-not-real-0123456789"


def _sign(core_mod, timestamp: int, body: bytes, secret: str = FAKE_SECRET) -> str:
    sig = core_mod.compute_signature(secret, timestamp, body)
    return f"t={timestamp},v1={sig}"


# --- happy path ------------------------------------------------------------


def test_valid_signature_passes(core_mod):
    body = b'{"event": "payment_intent.succeeded"}'
    header = _sign(core_mod, 1_000_000, body)
    core_mod.verify(body, header, FAKE_SECRET, now=1_000_000)  # must not raise


def test_valid_signature_within_tolerance_passes(core_mod):
    body = b"{}"
    header = _sign(core_mod, 1_000_000, body)
    core_mod.verify(body, header, FAKE_SECRET, tolerance_s=300, now=1_000_200)  # 200s later, within 300s


def test_multiple_v1_entries_any_match_passes(core_mod):
    # Stripe sends multiple v1= entries during a signing-secret rotation --
    # the OLD secret's signature is still one of the candidates.
    body = b"{}"
    old_secret = "whsec_old-fake-not-real"
    new_secret = "whsec_new-fake-not-real"
    old_sig = core_mod.compute_signature(old_secret, 1_000_000, body)
    new_sig = core_mod.compute_signature(new_secret, 1_000_000, body)
    header = f"t=1000000,v1={old_sig},v1={new_sig}"
    core_mod.verify(body, header, old_secret, now=1_000_000)  # must not raise


# --- tampering ---------------------------------------------------------


def test_tampered_body_fails(core_mod):
    body = b'{"amount": 100}'
    header = _sign(core_mod, 1_000_000, body)
    tampered = b'{"amount": 999999}'
    with pytest.raises(core_mod.SignatureMismatchError):
        core_mod.verify(tampered, header, FAKE_SECRET, now=1_000_000)


def test_wrong_secret_fails(core_mod):
    body = b"{}"
    header = _sign(core_mod, 1_000_000, body, secret=FAKE_SECRET)
    with pytest.raises(core_mod.SignatureMismatchError):
        core_mod.verify(body, header, "whsec_totally-different-fake", now=1_000_000)


# --- timestamp tolerance / replay window --------------------------------


def test_expired_timestamp_fails(core_mod):
    body = b"{}"
    header = _sign(core_mod, 1_000_000, body)
    with pytest.raises(core_mod.TimestampToleranceError):
        core_mod.verify(body, header, FAKE_SECRET, tolerance_s=300, now=1_000_600)  # 600s later


def test_future_timestamp_also_fails(core_mod):
    body = b"{}"
    header = _sign(core_mod, 1_000_600, body)
    with pytest.raises(core_mod.TimestampToleranceError):
        # signed timestamp is far in the "future" relative to now -- also rejected
        core_mod.verify(body, header, FAKE_SECRET, tolerance_s=300, now=1_000_000)


# --- header parsing / malformed input -----------------------------------


def test_missing_header_raises(core_mod):
    with pytest.raises(core_mod.MissingSignatureHeaderError):
        core_mod.verify(b"{}", None, FAKE_SECRET)


def test_empty_header_raises(core_mod):
    with pytest.raises(core_mod.MissingSignatureHeaderError):
        core_mod.verify(b"{}", "", FAKE_SECRET)


def test_header_missing_timestamp_raises(core_mod):
    with pytest.raises(core_mod.MalformedSignatureHeaderError):
        core_mod.verify(b"{}", "v1=deadbeef", FAKE_SECRET)


def test_header_missing_v1_raises(core_mod):
    with pytest.raises(core_mod.MalformedSignatureHeaderError):
        core_mod.verify(b"{}", "t=1000000", FAKE_SECRET)


def test_header_non_integer_timestamp_raises(core_mod):
    with pytest.raises(core_mod.MalformedSignatureHeaderError):
        core_mod.verify(b"{}", "t=not-a-number,v1=deadbeef", FAKE_SECRET)


def test_parse_stripe_style_header_shape(core_mod):
    parsed = core_mod.parse_stripe_style_header("t=1000000,v1=abc,v1=def")
    assert parsed.timestamp == 1_000_000
    assert parsed.signatures == ("abc", "def")


def test_parse_ignores_unknown_scheme_prefix(core_mod):
    # v0= is Stripe's older, deprecated scheme -- ignored, not treated as a
    # v1 candidate or a parse error.
    parsed = core_mod.parse_stripe_style_header("t=1000000,v0=legacy,v1=current")
    assert parsed.signatures == ("current",)


# --- constant-time comparison -------------------------------------------


def test_verify_uses_constant_time_compare(core_mod, monkeypatch):
    calls = []
    real_compare_digest = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real_compare_digest(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)

    body = b"{}"
    header = _sign(core_mod, 1_000_000, body)
    core_mod.verify(body, header, FAKE_SECRET, now=1_000_000)

    assert len(calls) >= 1  # hmac.compare_digest was actually reached, not a plain `==`


def test_verify_uses_constant_time_compare_on_failure_too(core_mod, monkeypatch):
    calls = []
    real_compare_digest = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: (calls.append(1), real_compare_digest(a, b))[1])

    body = b"{}"
    header = _sign(core_mod, 1_000_000, b"different-body")
    with pytest.raises(core_mod.SignatureMismatchError):
        core_mod.verify(body, header, FAKE_SECRET, now=1_000_000)

    assert len(calls) >= 1


# --- never logs the signature or secret ----------------------------------


def test_verify_itself_never_logs_anything(core_mod, caplog):
    """_core.py has no logger at all -- logging (by exception type only) is
    each framework adapter's responsibility, exercised in test_fastapi.py /
    test_django.py. This just pins that _core stays silent."""
    body = b"{}"
    header = _sign(core_mod, 1_000_000, body)
    with caplog.at_level(logging.DEBUG):
        core_mod.verify(body, header, FAKE_SECRET, now=1_000_000)
    assert caplog.text == ""


def test_exception_messages_never_contain_the_signature_or_secret(core_mod):
    body = b"{}"
    sig = core_mod.compute_signature(FAKE_SECRET, 1_000_000, body)
    header = f"t=1000000,v1={sig}"
    tampered = b"tampered"
    with pytest.raises(core_mod.SignatureMismatchError) as exc_info:
        core_mod.verify(tampered, header, FAKE_SECRET, now=1_000_000)
    message = str(exc_info.value)
    assert sig not in message
    assert FAKE_SECRET not in message
