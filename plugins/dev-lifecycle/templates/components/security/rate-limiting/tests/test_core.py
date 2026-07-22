"""Tests for rate-limiting's _core.py: refill math, burst behavior, per-key
isolation, and the XFF client-ip key function's trust posture."""

from __future__ import annotations


def test_first_request_is_allowed(core_mod):
    store = core_mod.InMemoryBucketStore()
    result = store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    assert result.allowed is True
    assert result.remaining == 4.0


def test_burst_up_to_capacity_then_denied(core_mod):
    store = core_mod.InMemoryBucketStore()
    for _ in range(5):
        result = store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
        assert result.allowed is True
    # 6th request in the same instant (no refill elapsed) is denied.
    result = store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    assert result.allowed is False
    assert result.retry_after > 0


def test_refill_math_is_deterministic(core_mod):
    store = core_mod.InMemoryBucketStore()
    # Drain the bucket completely.
    for _ in range(5):
        store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    denied = store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    assert denied.allowed is False

    # After 1 second at 1 token/sec, exactly one token has refilled --
    # exactly enough for one more request, then denied again.
    allowed = store.take("k1", capacity=5, refill_per_second=1.0, now=1.0)
    assert allowed.allowed is True
    denied_again = store.take("k1", capacity=5, refill_per_second=1.0, now=1.0)
    assert denied_again.allowed is False


def test_retry_after_shrinks_as_refill_time_elapses(core_mod):
    store = core_mod.InMemoryBucketStore()
    for _ in range(5):
        store.take("k1", capacity=5, refill_per_second=2.0, now=0.0)
    first = store.take("k1", capacity=5, refill_per_second=2.0, now=0.0)
    assert first.retry_after == 0.5  # need 1 token at 2/sec = 0.5s
    # Half a second later, the deficit (and thus retry_after) should have shrunk.
    later = store.take("k1", capacity=5, refill_per_second=2.0, now=0.25)
    assert later.retry_after < first.retry_after


def test_bucket_never_exceeds_capacity(core_mod):
    store = core_mod.InMemoryBucketStore()
    store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    # A huge elapsed time should cap tokens at capacity, not overflow past it.
    result = store.take("k1", capacity=5, refill_per_second=1.0, now=10_000.0)
    assert result.remaining <= 4.0  # capacity(5) - 1 just consumed


def test_per_key_isolation(core_mod):
    store = core_mod.InMemoryBucketStore()
    for _ in range(5):
        result = store.take("alice", capacity=5, refill_per_second=1.0, now=0.0)
        assert result.allowed is True
    denied = store.take("alice", capacity=5, refill_per_second=1.0, now=0.0)
    assert denied.allowed is False

    # A different key has its own full bucket, unaffected by "alice" being drained.
    other = store.take("bob", capacity=5, refill_per_second=1.0, now=0.0)
    assert other.allowed is True


def test_check_convenience_wrapper_uses_monotonic_by_default(core_mod):
    store = core_mod.InMemoryBucketStore()
    result = core_mod.check(store, "k1", capacity=5, refill_per_second=1.0)
    assert result.allowed is True


# --- client_ip_key: proxy-trust posture -----------------------------------


def test_client_ip_key_ignores_xff_by_default(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "1.2.3.4, 10.0.0.1")
    assert key == "10.0.0.1"  # untrusted by default -- the real peer address wins


def test_client_ip_key_uses_xff_when_trusted(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "1.2.3.4, 10.0.0.2", trust_proxy=True)
    assert key == "1.2.3.4"  # leftmost entry -- closest to the original client


def test_client_ip_key_falls_back_when_xff_absent_even_if_trusted(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", None, trust_proxy=True)
    assert key == "10.0.0.1"


def test_client_ip_key_falls_back_on_blank_xff(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "  , 10.0.0.2", trust_proxy=True)
    assert key == "10.0.0.1"
