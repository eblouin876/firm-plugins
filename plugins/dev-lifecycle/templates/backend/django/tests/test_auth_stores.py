"""Tests for `core/security/auth/stores.py` — the Django-async-ORM-backed
`DjangoUserStore`/`DjangoRefreshTokenStore` plus the token/password service
builders (Stage 5b, #44). These are STORE-level tests, one layer below
`AuthService` — the reuse-detection state machine itself is already
exhaustively covered by the vendored component's own `tests/test_core.py`
(run via `uv run` per that component's README); this module's job is
proving the Django-specific storage plumbing those tests assume actually
works: real rows, real soft-delete filtering, real autocommit durability.

**`@pytest.mark.django_db(transaction=True)` is REQUIRED on every test
here** — NOT pytest-django's own default (each test wrapped in one
`transaction.atomic()` block, rolled back at the end, no real commit ever
happens). Two independent reasons this module needs the real thing:

1. **Durability is the exact thing under test.** `DjangoRefreshTokenStore`'s
   own docstring (`stores.py`) is a whole argument that `add`/`mark_used`/
   `revoke_family` are durable BECAUSE Django autocommits every ORM write
   outside an explicit `atomic()` block — running these tests inside
   pytest-django's default per-test `atomic()` wrapper would make that
   claim untestable (every write would in fact be inside a transaction,
   the opposite of what's being verified) and, worse, could pass even if a
   future edit accidentally added a `transaction.atomic()` wrapper around
   these calls, since the outer test transaction would mask the bug.
2. **Django's async ORM misbehaves under a rolled-back `atomic()` block in
   practice** — `.acreate()`/`.afirst()`/`.aupdate()` internally bridge to
   a sync DB call via a thread; combined with pytest-django's default
   connection-per-test-wrapped-in-atomic() strategy, this combination is a
   known source of `SynchronousOnlyOperation`/connection-already-closed
   flakiness independent of this test module's own logic.
   `transaction=True` uses Django's `TransactionTestCase`-style reset
   (truncate tables between tests) instead, sidestepping both issues.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync

from core.models import RefreshToken, User
from core.security.auth import AuthService, InvalidToken, RefreshRecord, hash_token
from core.security.auth.stores import (
    AuthNotConfiguredError,
    DjangoRefreshTokenStore,
    DjangoUserStore,
    build_auth_service,
    get_password_service,
    get_token_service,
    utc_now,
)

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# DjangoUserStore
# ---------------------------------------------------------------------------


def test_create_persists_a_user_and_returns_a_matching_record() -> None:
    store = DjangoUserStore()
    record = async_to_sync(store.create)("alice@example.com", "hashed-password", ["admin"])

    assert record.email == "alice@example.com"
    assert record.password_hash == "hashed-password"
    assert record.roles == ("admin",)
    row = User.objects.get(id=uuid.UUID(record.id))
    assert row.email == "alice@example.com"
    assert row.roles == ["admin"]


def test_get_by_email_returns_the_matching_record() -> None:
    store = DjangoUserStore()
    created = async_to_sync(store.create)("bob@example.com", "hashed", [])

    found = async_to_sync(store.get_by_email)("bob@example.com")

    assert found is not None
    assert found.id == created.id
    assert found.email == "bob@example.com"


def test_get_by_email_unknown_returns_none() -> None:
    store = DjangoUserStore()
    assert async_to_sync(store.get_by_email)("nobody@example.com") is None


def test_get_by_id_returns_the_matching_record() -> None:
    store = DjangoUserStore()
    created = async_to_sync(store.create)("carol@example.com", "hashed", ["user"])

    found = async_to_sync(store.get_by_id)(created.id)

    assert found is not None
    assert found.email == "carol@example.com"
    assert found.roles == ("user",)


def test_get_by_id_unknown_uuid_returns_none() -> None:
    store = DjangoUserStore()
    assert async_to_sync(store.get_by_id)(str(uuid.uuid4())) is None


def test_get_by_id_malformed_id_returns_none_not_a_crash() -> None:
    store = DjangoUserStore()
    assert async_to_sync(store.get_by_id)("not-a-uuid") is None


def test_get_by_email_excludes_soft_deleted_users() -> None:
    """SECURITY (soft-delete auth-bypass fix, carried over from Stage 5a):
    a deactivated (soft-deleted) user must fail `get_by_email` — this is
    what makes `AuthService.login` reject a deactivated account instead of
    letting it log in."""
    store = DjangoUserStore()
    created = async_to_sync(store.create)("dana@example.com", "hashed", [])
    row = User.all_objects.get(id=uuid.UUID(created.id))
    row.mark_deleted()
    row.save(update_fields=["deleted_at"])

    assert async_to_sync(store.get_by_email)("dana@example.com") is None


def test_get_by_id_excludes_soft_deleted_users() -> None:
    """Same fix, the `get_by_id` half — this is what makes
    `AuthService.refresh` (step 6) reject a refresh for a deactivated
    account, closing the loop the login-side check alone wouldn't."""
    store = DjangoUserStore()
    created = async_to_sync(store.create)("erin@example.com", "hashed", [])
    row = User.all_objects.get(id=uuid.UUID(created.id))
    row.mark_deleted()
    row.save(update_fields=["deleted_at"])

    assert async_to_sync(store.get_by_id)(created.id) is None


# ---------------------------------------------------------------------------
# DjangoRefreshTokenStore
# ---------------------------------------------------------------------------


def _make_user() -> str:
    return async_to_sync(DjangoUserStore().create)(f"{uuid.uuid4().hex}@example.com", "hashed", []).id


def _make_record(user_id: str, *, family_id: str | None = None, raw_token: str | None = None) -> RefreshRecord:
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


def test_add_persists_a_row_get_by_hash_finds_it() -> None:
    store = DjangoRefreshTokenStore()
    user_id = _make_user()
    record = _make_record(user_id)

    async_to_sync(store.add)(record)
    found = async_to_sync(store.get_by_hash)(record.token_hash)

    assert found is not None
    assert found.token_hash == record.token_hash
    assert found.jti == record.jti
    assert found.family_id == record.family_id
    assert found.user_id == user_id
    assert found.used_at is None
    assert found.revoked is False
    # USE_TZ=True round-trips a tz-aware UTC datetime on sqlite too -- no
    # `_as_utc`-style normalization needed, see stores.py's `utc_now` docstring.
    assert found.issued_at.tzinfo is not None


def test_get_by_hash_unknown_returns_none() -> None:
    store = DjangoRefreshTokenStore()
    assert async_to_sync(store.get_by_hash)("unknown-hash") is None


def test_mark_used_sets_used_at() -> None:
    store = DjangoRefreshTokenStore()
    user_id = _make_user()
    record = _make_record(user_id)
    async_to_sync(store.add)(record)

    used_at = utc_now()
    async_to_sync(store.mark_used)(record.token_hash, used_at)

    row = RefreshToken.objects.get(token_hash=record.token_hash)
    assert row.used_at is not None
    assert abs((row.used_at - used_at).total_seconds()) < 1

    found = async_to_sync(store.get_by_hash)(record.token_hash)
    assert found is not None
    assert found.used_at is not None


def test_mark_used_on_unknown_hash_does_not_raise() -> None:
    store = DjangoRefreshTokenStore()
    async_to_sync(store.mark_used)("unknown-hash", utc_now())  # must not raise


def test_revoke_family_revokes_every_row_in_the_family() -> None:
    store = DjangoRefreshTokenStore()
    user_id = _make_user()
    family_id = uuid.uuid4().hex
    first = _make_record(user_id, family_id=family_id)
    second = _make_record(user_id, family_id=family_id)
    other_family = _make_record(user_id)

    async_to_sync(store.add)(first)
    async_to_sync(store.add)(second)
    async_to_sync(store.add)(other_family)

    async_to_sync(store.revoke_family)(family_id)

    first_found = async_to_sync(store.get_by_hash)(first.token_hash)
    second_found = async_to_sync(store.get_by_hash)(second.token_hash)
    other_found = async_to_sync(store.get_by_hash)(other_family.token_hash)
    assert first_found is not None and first_found.revoked is True
    assert second_found is not None and second_found.revoked is True
    # A different family's row is untouched.
    assert other_found is not None and other_found.revoked is False


def test_revoke_family_on_unknown_family_does_not_raise() -> None:
    store = DjangoRefreshTokenStore()
    async_to_sync(store.revoke_family)("unknown-family")  # must not raise


# ---------------------------------------------------------------------------
# Service builders
# ---------------------------------------------------------------------------


def test_get_password_service_is_a_process_wide_singleton() -> None:
    assert get_password_service() is get_password_service()


def test_get_token_service_builds_a_working_service(settings) -> None:
    settings.JWT_SIGNING_KEY = "a-real-test-signing-key-at-least-32-bytes-long"
    service = get_token_service()
    token = service.mint_access("some-user-id", ["admin"])
    claims = service.decode_access(token)
    assert claims.sub == "some-user-id"
    assert claims.roles == ["admin"]


@pytest.mark.parametrize("bad_key", [None, ""])
def test_get_token_service_raises_when_signing_key_is_unset(settings, bad_key) -> None:
    settings.JWT_SIGNING_KEY = bad_key
    with pytest.raises(AuthNotConfiguredError):
        get_token_service()


def test_build_auth_service_round_trips_register_login_refresh_logout(settings) -> None:
    """An end-to-end sanity check tying every piece in this module
    together through the real `AuthService` state machine (already
    exhaustively tested in isolation by the vendored component's own
    `tests/test_core.py`) — proving the Django plumbing this module adds
    is wired correctly, not re-testing the state machine's own logic."""
    settings.JWT_SIGNING_KEY = "a-real-test-signing-key-at-least-32-bytes-long"
    service = build_auth_service()
    assert isinstance(service, AuthService)

    async def _flow() -> None:
        await service.register("frank@example.com", "correct horse battery staple", roles=["user"])
        pair = await service.login("frank@example.com", "correct horse battery staple")
        claims = await service.resolve_access(pair.access)
        assert claims.sub is not None
        assert claims.roles == ["user"]

        rotated = await service.refresh(pair.refresh)
        assert rotated.refresh != pair.refresh

        await service.logout(rotated.refresh)
        with pytest.raises(InvalidToken):
            await service.refresh(rotated.refresh)

    async_to_sync(_flow)()
