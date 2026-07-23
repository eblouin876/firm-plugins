"""Tests for Stage 5c (#45)'s additions to `core/security/auth/stores.py`:
`DjangoSingleUseTokenStore`, `DjangoLockoutStore`, `DjangoUserStore.
mark_email_verified`/`set_password_hash`, `DjangoRefreshTokenStore.
revoke_all_for_user`, and the `build_lockout_policy`/`build_account_service`
factories. Same `tests/test_auth_stores.py`-style module -- deliberately a
SEPARATE file (not appended to that one) so the Stage 5b vs. Stage 5c
plumbing each has its own focused module, mirroring how `_core.py` itself
grew `AccountService` ALONGSIDE `AuthService` rather than folding into it.

**`@pytest.mark.django_db(transaction=True)` is REQUIRED on every test
here** — for the SAME two reasons `tests/test_auth_stores.py`'s own module
docstring documents (durability is the exact thing several tests below are
proving; Django's async ORM misbehaves under pytest-django's default
per-test rolled-back `atomic()` wrapper). See that module's docstring for
the full rationale."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync

from core.models import LoginAttempt, SingleUseToken, User
from core.security.auth import (
    AccountService,
    AttemptRecord,
    InvalidSingleUseToken,
    LockoutPolicy,
    RefreshRecord,
    SingleUseTokenService,
    hash_token,
)
from core.security.auth.stores import (
    DjangoLockoutStore,
    DjangoRefreshTokenStore,
    DjangoSingleUseTokenStore,
    DjangoUserStore,
    build_account_service,
    build_lockout_policy,
    utc_now,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _make_user(email: str | None = None) -> str:
    return async_to_sync(DjangoUserStore().create)(email or f"{uuid.uuid4().hex}@example.com", "hashed", []).id


# ---------------------------------------------------------------------------
# DjangoSingleUseTokenStore / SingleUseTokenService round-trip
# ---------------------------------------------------------------------------


def test_single_use_token_issue_and_consume_round_trips() -> None:
    user_id = _make_user()
    service = SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now)

    raw = async_to_sync(service.issue)(user_id, "verify", timedelta(hours=24))

    row = SingleUseToken.objects.get(user_id=uuid.UUID(user_id))
    assert row.token_hash == hash_token(raw)
    assert row.token_hash != raw  # the raw token is never stored
    assert row.purpose == "verify"
    assert row.used_at is None

    consumed_user_id = async_to_sync(service.consume)(raw, "verify")
    assert consumed_user_id == user_id

    row.refresh_from_db()
    assert row.used_at is not None


def test_single_use_token_reuse_is_rejected() -> None:
    """A second presentation of an already-consumed token is rejected --
    `used_at` is retained, not cleared/deleted, on first consume (see
    `_core.SingleUseTokenRecord`'s own docstring)."""
    user_id = _make_user()
    service = SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now)
    raw = async_to_sync(service.issue)(user_id, "reset", timedelta(hours=1))

    async_to_sync(service.consume)(raw, "reset")

    with pytest.raises(InvalidSingleUseToken):
        async_to_sync(service.consume)(raw, "reset")


def test_single_use_token_wrong_purpose_is_rejected() -> None:
    user_id = _make_user()
    service = SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now)
    raw = async_to_sync(service.issue)(user_id, "verify", timedelta(hours=24))

    with pytest.raises(InvalidSingleUseToken):
        async_to_sync(service.consume)(raw, "reset")


def test_single_use_token_expired_is_rejected() -> None:
    user_id = _make_user()
    service = SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now)
    raw = async_to_sync(service.issue)(user_id, "verify", timedelta(seconds=-1))

    with pytest.raises(InvalidSingleUseToken):
        async_to_sync(service.consume)(raw, "verify")


def test_single_use_token_unknown_raw_is_rejected() -> None:
    service = SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now)
    with pytest.raises(InvalidSingleUseToken):
        async_to_sync(service.consume)("never-issued-raw-token", "verify")


def test_single_use_token_get_by_hash_unknown_returns_none() -> None:
    store = DjangoSingleUseTokenStore()
    assert async_to_sync(store.get_by_hash)("unknown-hash") is None


def test_single_use_token_mark_used_on_unknown_hash_does_not_raise() -> None:
    store = DjangoSingleUseTokenStore()
    async_to_sync(store.mark_used)("unknown-hash", utc_now())  # must not raise


# ---------------------------------------------------------------------------
# DjangoLockoutStore / LockoutPolicy -- durability across a fresh connection
# ---------------------------------------------------------------------------


def _policy(store: DjangoLockoutStore, *, max_failures: int = 3) -> LockoutPolicy:
    return LockoutPolicy(
        store,
        max_failures=max_failures,
        lockout_duration=timedelta(minutes=15),
        window=timedelta(minutes=15),
        now=utc_now,
    )


def test_lockout_survives_a_fresh_connection() -> None:
    """DB-backed durability -- the same property `SqlAlchemyLockoutStore`'s
    own docstring says the real-PG16 integration proves directly: write an
    `AttemptRecord` via one store instance, close the connection, then read
    it back through a BRAND NEW `DjangoLockoutStore`/`LockoutPolicy`
    instance (standing in for a fresh connection / a different worker
    process picking up a later request) and see the lock still there."""
    from django.db import close_old_connections

    account_key = str(uuid.uuid4())
    policy = _policy(DjangoLockoutStore(), max_failures=3)

    for _ in range(3):
        async_to_sync(policy.record_failure)(account_key)
    assert async_to_sync(policy.is_locked)(account_key) is True

    close_old_connections()

    fresh_policy = _policy(DjangoLockoutStore(), max_failures=3)
    assert async_to_sync(fresh_policy.is_locked)(account_key) is True

    row = LoginAttempt.objects.get(account_key=account_key)
    assert row.failure_count == 3
    assert row.locked_until is not None


def test_lockout_clear_removes_the_row() -> None:
    account_key = str(uuid.uuid4())
    store = DjangoLockoutStore()
    now = utc_now()
    async_to_sync(store.upsert)(
        AttemptRecord(
            account_key=account_key,
            failure_count=1,
            first_failure_at=now,
            last_failure_at=now,
            locked_until=None,
        )
    )
    assert LoginAttempt.objects.filter(account_key=account_key).exists()

    async_to_sync(store.clear)(account_key)

    assert not LoginAttempt.objects.filter(account_key=account_key).exists()


def test_lockout_clear_unknown_account_key_does_not_raise() -> None:
    store = DjangoLockoutStore()
    async_to_sync(store.clear)("unknown-account-key")  # must not raise


def test_lockout_get_unknown_account_key_returns_none() -> None:
    store = DjangoLockoutStore()
    assert async_to_sync(store.get)("unknown-account-key") is None


def test_build_lockout_policy_returns_none_when_disabled(settings) -> None:
    settings.AUTH_LOCKOUT_ENABLED = False
    assert build_lockout_policy() is None


def test_build_lockout_policy_returns_a_working_policy(settings) -> None:
    settings.AUTH_LOCKOUT_ENABLED = True
    settings.AUTH_LOCKOUT_MAX_FAILURES = 2
    settings.AUTH_LOCKOUT_DURATION_SECONDS = 900
    settings.AUTH_LOCKOUT_WINDOW_SECONDS = 900
    policy = build_lockout_policy()
    assert policy is not None

    account_key = str(uuid.uuid4())
    async_to_sync(policy.record_failure)(account_key)
    async_to_sync(policy.record_failure)(account_key)

    assert async_to_sync(policy.is_locked)(account_key) is True


# ---------------------------------------------------------------------------
# DjangoUserStore.mark_email_verified / set_password_hash
# ---------------------------------------------------------------------------


def test_mark_email_verified_sets_flag_and_timestamp() -> None:
    store = DjangoUserStore()
    created = async_to_sync(store.create)("henry@example.com", "hashed", [])
    assert created.email_verified is False

    at = utc_now()
    async_to_sync(store.mark_email_verified)(created.id, at)

    row = User.objects.get(id=uuid.UUID(created.id))
    assert row.email_verified is True
    assert row.verified_at is not None

    found = async_to_sync(store.get_by_email)("henry@example.com")
    assert found is not None
    assert found.email_verified is True


def test_set_password_hash_overwrites_stored_hash() -> None:
    store = DjangoUserStore()
    created = async_to_sync(store.create)("iris@example.com", "old-hash", [])

    async_to_sync(store.set_password_hash)(created.id, "new-hash")

    row = User.objects.get(id=uuid.UUID(created.id))
    assert row.password_hash == "new-hash"


def test_mark_email_verified_malformed_id_does_not_raise() -> None:
    store = DjangoUserStore()
    async_to_sync(store.mark_email_verified)("not-a-uuid", utc_now())  # must not raise


def test_set_password_hash_malformed_id_does_not_raise() -> None:
    store = DjangoUserStore()
    async_to_sync(store.set_password_hash)("not-a-uuid", "whatever")  # must not raise


def test_mark_email_verified_excludes_soft_deleted_users() -> None:
    """SECURITY: the SAME soft-delete scoping `test_auth_stores.py`'s own
    `get_by_email`/`get_by_id` tests prove -- `mark_email_verified` goes
    through `User.objects` (soft-delete-scoped), so it must be a no-op
    against a deactivated user's row rather than silently reviving their
    ability to satisfy `AuthService.login`'s `require_verification` gate."""
    store = DjangoUserStore()
    created = async_to_sync(store.create)("frank@example.com", "hashed", [])
    row = User.all_objects.get(id=uuid.UUID(created.id))
    row.mark_deleted()
    row.save(update_fields=["deleted_at"])

    async_to_sync(store.mark_email_verified)(created.id, utc_now())

    row.refresh_from_db()
    assert row.email_verified is False
    assert row.verified_at is None


def test_set_password_hash_excludes_soft_deleted_users() -> None:
    """SECURITY: same soft-delete scoping, the `set_password_hash` half --
    a deactivated user's stored hash must not be reachable for a reset."""
    store = DjangoUserStore()
    created = async_to_sync(store.create)("grace@example.com", "hashed-original", [])
    row = User.all_objects.get(id=uuid.UUID(created.id))
    row.mark_deleted()
    row.save(update_fields=["deleted_at"])

    async_to_sync(store.set_password_hash)(created.id, "hashed-new")

    row.refresh_from_db()
    assert row.password_hash == "hashed-original"


# ---------------------------------------------------------------------------
# DjangoRefreshTokenStore.revoke_all_for_user
# ---------------------------------------------------------------------------


def _refresh_record(user_id: str, *, family_id: str | None = None, raw_token: str | None = None) -> RefreshRecord:
    now = utc_now()
    raw = raw_token or uuid.uuid4().hex
    return RefreshRecord(
        token_hash=hash_token(raw),
        jti=uuid.uuid4().hex,
        family_id=family_id or uuid.uuid4().hex,
        user_id=user_id,
        issued_at=now,
        expires_at=now + timedelta(days=14),
        used_at=None,
        revoked=False,
    )


def test_revoke_all_for_user_revokes_every_family() -> None:
    user_id = _make_user()
    other_user_id = _make_user()
    store = DjangoRefreshTokenStore()

    fam_a = _refresh_record(user_id)
    fam_b = _refresh_record(user_id)
    other_users_token = _refresh_record(other_user_id)
    async_to_sync(store.add)(fam_a)
    async_to_sync(store.add)(fam_b)
    async_to_sync(store.add)(other_users_token)

    async_to_sync(store.revoke_all_for_user)(user_id)

    found_a = async_to_sync(store.get_by_hash)(fam_a.token_hash)
    found_b = async_to_sync(store.get_by_hash)(fam_b.token_hash)
    found_other = async_to_sync(store.get_by_hash)(other_users_token.token_hash)
    assert found_a is not None and found_a.revoked is True
    assert found_b is not None and found_b.revoked is True
    # A different user's token is untouched.
    assert found_other is not None and found_other.revoked is False


# ---------------------------------------------------------------------------
# build_account_service -- wiring sanity check
# ---------------------------------------------------------------------------


def test_build_account_service_returns_a_working_account_service() -> None:
    """End-to-end sanity check tying the DjangoUserStore/
    DjangoSingleUseTokenStore/DjangoRefreshTokenStore plumbing together
    through the real `AccountService.verify_email` -- proving the wiring
    this module adds is correct, not re-testing `_core.py`'s own
    `AccountService` logic (already exhaustively covered by the vendored
    component's own test suite). No `JWT_SIGNING_KEY` needed --
    `build_account_service()` has no `TokenService` dependency at all,
    unlike `build_auth_service()`."""
    service = build_account_service()
    assert isinstance(service, AccountService)

    async def _flow() -> None:
        user = await DjangoUserStore().create("liam@example.com", "hashed", ["user"])
        assert user.email_verified is False

        # Issue a "verify" token directly against the SAME
        # DjangoSingleUseTokenStore build_account_service wires into the
        # service's own `tokens` attribute -- bypasses request_email_
        # verification's own (fire-and-forget, backgrounded) email send,
        # which this test isn't trying to observe.
        raw = await SingleUseTokenService(DjangoSingleUseTokenStore(), now=utc_now).issue(
            user.id, "verify", timedelta(hours=24)
        )
        await service.verify_email(raw)

    async_to_sync(_flow)()

    row = User.objects.get(email="liam@example.com")
    assert row.email_verified is True
    assert row.verified_at is not None
