"""Tests for the audit-logging drop-in. Values used throughout are
obviously fake (e.g. "hunter2-not-real") — no real credential ever
appears in this file.
"""

from __future__ import annotations

import json
import logging

import pytest

from audit import (
    DEFAULT_SENSITIVE_KEYS,
    REDACTED,
    audit_event,
    bind_request_id,
    redact,
    request_id_var,
)


@pytest.fixture(autouse=True)
def _clean_request_id_context():
    """Every test starts with no ambient request id bound, and leaves none
    behind for the next test — the contextvar default is None."""
    token = request_id_var.set(None)
    yield
    request_id_var.reset(token)


# --- schema shape --------------------------------------------------------


def test_audit_event_returns_stable_schema_keys():
    record = audit_event(
        "user.login",
        actor="user:42",
        resource="session:abc123",
        outcome="success",
    )
    assert set(record.keys()) == {"ts", "action", "actor", "resource", "outcome", "request_id", "extra"}
    assert record["action"] == "user.login"
    assert record["actor"] == "user:42"
    assert record["resource"] == "session:abc123"
    assert record["outcome"] == "success"


def test_audit_event_ts_is_iso8601_utc():
    record = audit_event("user.login", actor="user:1", resource="session:1", outcome="success")
    # Fails loudly (ValueError) if it isn't a real ISO-8601 timestamp.
    from datetime import datetime

    parsed = datetime.fromisoformat(record["ts"])
    assert parsed.tzinfo is not None


def test_audit_event_logs_valid_json(caplog):
    with caplog.at_level(logging.INFO, logger="audit"):
        audit_event("invoice.export", actor="user:7", resource="invoice:9", outcome="success")
    assert len(caplog.records) == 1
    logged = json.loads(caplog.records[0].message)
    assert logged["action"] == "invoice.export"
    assert logged["resource"] == "invoice:9"


# --- request id: explicit, contextvar fallback, override -----------------


def test_audit_event_defaults_request_id_to_none_when_unbound():
    record = audit_event("user.login", actor="user:1", resource="session:1", outcome="success")
    assert record["request_id"] is None


def test_audit_event_uses_bound_request_id_from_contextvar():
    token = bind_request_id("req-fake-abc123")
    try:
        record = audit_event("user.login", actor="user:1", resource="session:1", outcome="success")
    finally:
        request_id_var.reset(token)
    assert record["request_id"] == "req-fake-abc123"


def test_audit_event_explicit_request_id_overrides_contextvar():
    token = bind_request_id("req-from-middleware")
    try:
        record = audit_event(
            "user.login",
            actor="user:1",
            resource="session:1",
            outcome="success",
            request_id="req-explicit-override",
        )
    finally:
        request_id_var.reset(token)
    assert record["request_id"] == "req-explicit-override"


# --- redaction: actually redacts, doesn't leak into the log line ---------


def test_redact_replaces_configured_sensitive_keys():
    payload = {"password": "hunter2-not-real", "username": "alice"}
    result = redact(payload)
    assert result["password"] == REDACTED
    assert result["username"] == "alice"


def test_redact_is_case_insensitive():
    payload = {"PASSWORD": "hunter2-not-real", "Api_Key": "fake-key-123"}
    result = redact(payload)
    assert result["PASSWORD"] == REDACTED
    assert result["Api_Key"] == REDACTED


def test_redact_recurses_into_nested_mappings():
    payload = {"user": {"name": "alice", "token": "fake-nested-token"}}
    result = redact(payload)
    assert result["user"]["name"] == "alice"
    assert result["user"]["token"] == REDACTED


def test_redact_does_not_mutate_original():
    payload = {"password": "hunter2-not-real"}
    redact(payload)
    assert payload["password"] == "hunter2-not-real"  # original untouched


def test_audit_event_redacts_extra_before_logging(caplog):
    with caplog.at_level(logging.INFO, logger="audit"):
        record = audit_event(
            "user.update",
            actor="user:1",
            resource="user:1",
            outcome="success",
            password="hunter2-not-real",
            display_name="alice",
        )
    assert record["extra"]["password"] == REDACTED
    assert record["extra"]["display_name"] == "alice"
    # And critically: the raw value never reaches the actual log line.
    assert "hunter2-not-real" not in caplog.text


def test_audit_event_call_site_can_extend_sensitive_keys(caplog):
    custom_keys = DEFAULT_SENSITIVE_KEYS | {"internal_note"}
    with caplog.at_level(logging.INFO, logger="audit"):
        record = audit_event(
            "user.update",
            actor="user:1",
            resource="user:1",
            outcome="success",
            sensitive_keys=custom_keys,
            internal_note="do not log this fake note",
        )
    assert record["extra"]["internal_note"] == REDACTED
    assert "do not log this fake note" not in caplog.text
