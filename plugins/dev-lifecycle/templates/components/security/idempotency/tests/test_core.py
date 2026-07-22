"""Tests for idempotency's _core.py: key validation, fingerprinting,
replay/conflict outcomes, and storage isolation."""

from __future__ import annotations

import logging

import pytest


# --- key validation ---------------------------------------------------------


def test_valid_key_passes_through_unchanged(core_mod):
    assert core_mod.validate_key("order-123_retry.1") == "order-123_retry.1"


def test_missing_key_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key(None)


def test_empty_key_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key("")


def test_overlong_key_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key("a" * (core_mod.MAX_KEY_LENGTH + 1))


def test_key_at_max_length_passes(core_mod):
    key = "a" * core_mod.MAX_KEY_LENGTH
    assert core_mod.validate_key(key) == key


def test_key_with_unsafe_character_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key("order 123")  # space


def test_key_with_control_character_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key("order\n123")


def test_key_with_quote_or_special_char_raises(core_mod):
    with pytest.raises(core_mod.InvalidIdempotencyKeyError):
        core_mod.validate_key("order/123;drop-table")


def test_invalid_key_error_never_echoes_the_raw_value(core_mod):
    raw = "bad key with spaces"
    with pytest.raises(core_mod.InvalidIdempotencyKeyError) as exc_info:
        core_mod.validate_key(raw)
    assert raw not in str(exc_info.value)


# --- fingerprinting ----------------------------------------------------------


def test_fingerprint_is_deterministic(core_mod):
    a = core_mod.compute_fingerprint("POST", "/orders", b'{"amount": 100}')
    b = core_mod.compute_fingerprint("POST", "/orders", b'{"amount": 100}')
    assert a == b


def test_fingerprint_differs_on_body(core_mod):
    a = core_mod.compute_fingerprint("POST", "/orders", b'{"amount": 100}')
    b = core_mod.compute_fingerprint("POST", "/orders", b'{"amount": 999}')
    assert a != b


def test_fingerprint_differs_on_method(core_mod):
    a = core_mod.compute_fingerprint("POST", "/orders", b"{}")
    b = core_mod.compute_fingerprint("PUT", "/orders", b"{}")
    assert a != b


def test_fingerprint_differs_on_path(core_mod):
    a = core_mod.compute_fingerprint("POST", "/orders", b"{}")
    b = core_mod.compute_fingerprint("POST", "/refunds", b"{}")
    assert a != b


def test_fingerprint_method_is_case_insensitive(core_mod):
    a = core_mod.compute_fingerprint("post", "/orders", b"{}")
    b = core_mod.compute_fingerprint("POST", "/orders", b"{}")
    assert a == b


# --- check() / record_response(): replay + conflict --------------------------


def test_check_on_unseen_key_returns_new_outcome(core_mod, store):
    outcome = core_mod.check(store, "key-1", "fp-1")
    assert outcome.is_replay is False
    assert outcome.stored_response is None


def test_replay_returns_stored_response_for_same_fingerprint(core_mod, store):
    response = core_mod.StoredResponse(status_code=200, headers=(("x-a", "1"),), body=b"hello")
    core_mod.record_response(store, "key-1", "fp-1", response)

    outcome = core_mod.check(store, "key-1", "fp-1")
    assert outcome.is_replay is True
    assert outcome.stored_response == response


def test_conflict_raised_for_same_key_different_fingerprint(core_mod, store):
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"hello")
    core_mod.record_response(store, "key-1", "fp-1", response)

    with pytest.raises(core_mod.IdempotencyConflictError):
        core_mod.check(store, "key-1", "fp-2")


def test_conflict_error_never_echoes_key_or_fingerprint(core_mod, store):
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"hello")
    core_mod.record_response(store, "super-secret-order-key", "fp-1", response)

    with pytest.raises(core_mod.IdempotencyConflictError) as exc_info:
        core_mod.check(store, "super-secret-order-key", "fp-2")
    message = str(exc_info.value)
    assert "super-secret-order-key" not in message
    assert "fp-1" not in message
    assert "fp-2" not in message


def test_nothing_in_this_module_logs_the_key_value(core_mod, caplog):
    """_core.py has no logger at all -- logging (by exception type only)
    is each framework adapter's responsibility, matching
    webhook-signature's _core/adapter split."""
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"hello")
    fresh_store = core_mod.InMemoryIdempotencyStore()
    with caplog.at_level(logging.DEBUG):
        core_mod.record_response(fresh_store, "a-key-value", "fp-1", response)
        core_mod.check(fresh_store, "a-key-value", "fp-1")
    assert caplog.text == ""


# --- storage isolation --------------------------------------------------------


def test_different_keys_are_isolated_in_the_same_store(core_mod, store):
    response_a = core_mod.StoredResponse(status_code=200, headers=(), body=b"a")
    response_b = core_mod.StoredResponse(status_code=201, headers=(), body=b"b")
    core_mod.record_response(store, "key-a", "fp-a", response_a)
    core_mod.record_response(store, "key-b", "fp-b", response_b)

    assert core_mod.check(store, "key-a", "fp-a").stored_response == response_a
    assert core_mod.check(store, "key-b", "fp-b").stored_response == response_b


def test_separate_store_instances_do_not_share_state(core_mod):
    store_one = core_mod.InMemoryIdempotencyStore()
    store_two = core_mod.InMemoryIdempotencyStore()
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"hello")

    core_mod.record_response(store_one, "key-1", "fp-1", response)

    assert store_one.get("key-1") is not None
    assert store_two.get("key-1") is None


def test_in_memory_store_get_returns_none_for_unknown_key(core_mod, store):
    assert store.get("never-seen") is None


# --- Redis stub never imports redis, always raises ----------------------------


def test_redis_store_is_a_stub_that_raises_on_construction(core_mod):
    with pytest.raises(NotImplementedError):
        core_mod.RedisIdempotencyStore()


def test_no_redis_module_imported_anywhere(core_mod):
    import sys

    assert "redis" not in sys.modules
