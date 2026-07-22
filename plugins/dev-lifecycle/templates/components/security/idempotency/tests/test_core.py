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


# --- BLOCKER-1: compute_storage_key() principal scoping ---------------------


def test_compute_storage_key_differs_for_different_principals_same_key(core_mod):
    a = core_mod.compute_storage_key("alice", "shared-key")
    b = core_mod.compute_storage_key("bob", "shared-key")
    assert a != b


def test_compute_storage_key_is_deterministic(core_mod):
    a = core_mod.compute_storage_key("alice", "order-1")
    b = core_mod.compute_storage_key("alice", "order-1")
    assert a == b


def test_compute_storage_key_does_not_collide_across_the_separator(core_mod):
    # "a" + NUL + "bc" must not equal "ab" + NUL + "c" -- the composed
    # inputs must not collide just because concatenation without a
    # separator would.
    a = core_mod.compute_storage_key("a", "bc")
    b = core_mod.compute_storage_key("ab", "c")
    assert a != b


def test_check_and_record_response_use_the_composed_storage_key(core_mod, store):
    """Demonstrates the full cross-principal-safety property at the
    check()/record_response() level (the adapters' actual call pattern):
    the same idempotency key from two different principals produces two
    independent records, so the second principal's request is NOT treated
    as a replay of the first's."""
    alice_key = core_mod.compute_storage_key("alice", "shared-key")
    bob_key = core_mod.compute_storage_key("bob", "shared-key")

    alice_outcome = core_mod.check(store, alice_key, "fp-1")
    assert alice_outcome.is_replay is False
    core_mod.record_response(
        store, alice_key, "fp-1", core_mod.StoredResponse(status_code=200, headers=(), body=b"alice")
    )

    bob_outcome = core_mod.check(store, bob_key, "fp-1")
    assert bob_outcome.is_replay is False  # NOT a replay of alice's response


# --- HIGH-2: sensitive headers are stripped before storage ------------------


def test_record_response_strips_set_cookie(core_mod, store):
    response = core_mod.StoredResponse(
        status_code=200, headers=(("Set-Cookie", "session=abc"), ("X-Other", "1")), body=b"ok"
    )
    core_mod.record_response(store, "key-1", "fp-1", response)
    stored = store.get("key-1")
    header_names = {name.lower() for name, _ in stored.response.headers}
    assert "set-cookie" not in header_names
    assert "x-other" in header_names


def test_record_response_strips_every_denylisted_header(core_mod, store):
    headers = tuple((name, "value") for name in core_mod.REPLAY_HEADER_DENYLIST) + (("Content-Type", "text/plain"),)
    response = core_mod.StoredResponse(status_code=200, headers=headers, body=b"ok")
    core_mod.record_response(store, "key-1", "fp-1", response)
    stored = store.get("key-1")
    header_names = {name.lower() for name, _ in stored.response.headers}
    assert header_names == {"content-type"}


def test_strip_non_replayable_headers_is_case_insensitive(core_mod):
    filtered = core_mod.strip_non_replayable_headers((("SET-COOKIE", "x"), ("Content-Type", "y")))
    assert filtered == (("Content-Type", "y"),)


# --- LOW-9: InMemoryIdempotencyStore TTL / cap eviction ---------------------


def test_stale_record_is_evicted_after_ttl(core_mod, monkeypatch):
    # get() (unlike put(), which takes an explicit `now`) reads the real
    # wall clock via `time.time()` -- monkeypatch it for a deterministic
    # "current time" on the read side too.
    fake_now = [0.0]
    monkeypatch.setattr(core_mod.time, "time", lambda: fake_now[0])

    store = core_mod.InMemoryIdempotencyStore(ttl_seconds=100.0)
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"ok")
    core_mod.record_response(store, "key-1", "fp-1", response, now=0.0)

    # Still within TTL.
    fake_now[0] = 50.0
    core_mod.record_response(store, "key-2", "fp-1", response, now=50.0)
    assert store.get("key-1") is not None

    # Past TTL relative to key-1's creation -- next access sweeps it.
    fake_now[0] = 200.0
    core_mod.record_response(store, "key-3", "fp-1", response, now=200.0)
    assert store.get("key-1") is None
    assert store.get("key-3") is not None  # the fresh record survives


def test_ttl_disabled_when_zero_or_negative(core_mod, monkeypatch):
    monkeypatch.setattr(core_mod.time, "time", lambda: 1_000_000.0)
    store = core_mod.InMemoryIdempotencyStore(ttl_seconds=0)
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"ok")
    core_mod.record_response(store, "key-1", "fp-1", response, now=0.0)
    core_mod.record_response(store, "key-2", "fp-1", response, now=1_000_000.0)
    assert store.get("key-1") is not None  # never swept when ttl_seconds <= 0


def test_max_keys_cap_evicts_oldest(core_mod, monkeypatch):
    monkeypatch.setattr(core_mod.time, "time", lambda: 2.0)
    store = core_mod.InMemoryIdempotencyStore(ttl_seconds=10_000.0, max_keys=2)
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"ok")
    core_mod.record_response(store, "key-1", "fp-1", response, now=0.0)
    core_mod.record_response(store, "key-2", "fp-1", response, now=1.0)
    core_mod.record_response(store, "key-3", "fp-1", response, now=2.0)

    assert store.get("key-1") is None  # oldest, evicted over the cap
    assert store.get("key-2") is not None
    assert store.get("key-3") is not None


def test_max_keys_disabled_by_default(core_mod, monkeypatch):
    monkeypatch.setattr(core_mod.time, "time", lambda: 49.0)
    store = core_mod.InMemoryIdempotencyStore(ttl_seconds=10_000.0)
    response = core_mod.StoredResponse(status_code=200, headers=(), body=b"ok")
    for i in range(50):
        core_mod.record_response(store, f"key-{i}", "fp-1", response, now=float(i))
    assert store.get("key-0") is not None  # nothing evicted without max_keys set
