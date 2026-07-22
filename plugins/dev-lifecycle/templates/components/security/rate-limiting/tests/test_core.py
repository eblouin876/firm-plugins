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


# --- client_ip_key: proxy-trust posture (HIGH-3: rightmost-minus-hops) -----


def test_client_ip_key_ignores_xff_by_default(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "1.2.3.4, 10.0.0.1")
    assert key == "10.0.0.1"  # trusted_hops=0 by default -- the real peer address wins


def test_client_ip_key_uses_rightmost_entry_when_one_hop_trusted(core_mod):
    # ALB directly in front of the app appends its own observed peer
    # address as the LAST (rightmost) entry -- trusted_hops=1 reads that.
    key = core_mod.client_ip_key("10.0.0.1", "1.2.3.4, 5.6.7.8", trusted_hops=1)
    assert key == "5.6.7.8"


def test_client_ip_key_spoofed_leftmost_entry_does_not_change_the_key(core_mod):
    """The load-bearing regression test for HIGH-3: an attacker fully
    controls everything EXCEPT the rightmost entry (which the trusted
    proxy appends) -- varying only the client-supplied leftmost entry must
    never change the selected key when trusted_hops=1."""
    real_client_seen_by_alb = "5.6.7.8"
    key_a = core_mod.client_ip_key(
        "10.0.0.1", f"1.2.3.4, {real_client_seen_by_alb}", trusted_hops=1
    )
    key_b = core_mod.client_ip_key(
        "10.0.0.1", f"9.9.9.9, {real_client_seen_by_alb}", trusted_hops=1
    )
    assert key_a == key_b == real_client_seen_by_alb


def test_client_ip_key_two_trusted_hops_takes_second_from_right(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "1.2.3.4, 5.6.7.8, 9.9.9.9", trusted_hops=2)
    assert key == "5.6.7.8"


def test_client_ip_key_falls_back_when_xff_absent_even_if_trusted(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", None, trusted_hops=1)
    assert key == "10.0.0.1"


def test_client_ip_key_falls_back_on_blank_xff(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "  ,", trusted_hops=1)
    assert key == "10.0.0.1"


def test_client_ip_key_falls_back_when_fewer_entries_than_trusted_hops(core_mod):
    key = core_mod.client_ip_key("10.0.0.1", "5.6.7.8", trusted_hops=2)
    assert key == "10.0.0.1"  # insufficient header -- cannot verify, fall back safely


def test_client_ip_key_peer_ip_default_is_unchanged_by_the_fix(core_mod):
    # A plain, unproxied request (no trusted_hops passed at all) still
    # behaves exactly as before the fix.
    key = core_mod.client_ip_key("203.0.113.5", None)
    assert key == "203.0.113.5"


# --- validate_refill_rate (MEDIUM-7) ----------------------------------------


def test_validate_refill_rate_rejects_zero(core_mod):
    import pytest

    with pytest.raises(ValueError):
        core_mod.validate_refill_rate(0)


def test_validate_refill_rate_rejects_negative(core_mod):
    import pytest

    with pytest.raises(ValueError):
        core_mod.validate_refill_rate(-1.0)


def test_validate_refill_rate_accepts_positive(core_mod):
    core_mod.validate_refill_rate(1.0)  # must not raise


# --- InMemoryBucketStore idle-eviction / cap (HIGH-4) -----------------------


def test_stale_bucket_is_evicted_after_ttl(core_mod):
    store = core_mod.InMemoryBucketStore(ttl_seconds=100.0)
    store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    assert "k1" in store._buckets

    # Still within TTL -- a touch on a different key must not evict k1.
    store.take("k2", capacity=5, refill_per_second=1.0, now=50.0)
    assert "k1" in store._buckets

    # Past TTL relative to k1's last touch -- the next access sweeps it.
    store.take("k3", capacity=5, refill_per_second=1.0, now=200.0)
    assert "k1" not in store._buckets
    assert "k3" in store._buckets


def test_ttl_disabled_when_zero_or_negative(core_mod):
    store = core_mod.InMemoryBucketStore(ttl_seconds=0)
    store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    store.take("k2", capacity=5, refill_per_second=1.0, now=1_000_000.0)
    assert "k1" in store._buckets  # never swept when ttl_seconds <= 0


def test_max_keys_cap_evicts_oldest(core_mod):
    store = core_mod.InMemoryBucketStore(ttl_seconds=10_000.0, max_keys=2)
    store.take("k1", capacity=5, refill_per_second=1.0, now=0.0)
    store.take("k2", capacity=5, refill_per_second=1.0, now=1.0)
    store.take("k3", capacity=5, refill_per_second=1.0, now=2.0)

    assert "k1" not in store._buckets  # oldest, evicted over the cap
    assert "k2" in store._buckets
    assert "k3" in store._buckets


def test_max_keys_disabled_by_default(core_mod):
    store = core_mod.InMemoryBucketStore(ttl_seconds=10_000.0)
    for i in range(50):
        store.take(f"k{i}", capacity=5, refill_per_second=1.0, now=float(i))
    assert "k0" in store._buckets  # nothing evicted without max_keys set
