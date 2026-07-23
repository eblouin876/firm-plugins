"""App-specific SQLAlchemy-backed implementations of the vendored auth
component's `UserStore`/`RefreshTokenStore` protocols (`_core.py`), plus
the app-level `PasswordService`/`TokenService` construction this block's
`app/api/deps.py:get_auth_service` binds into a per-request `AuthService`.

**NOT a vendored file** — it lives alongside `_core.py`/`fastapi.py`/
`__init__.py` in this directory because that is where this app's auth
wiring naturally sits, but it imports `app.models` and `app.core.config`,
so it is ordinary app code (see `__init__.py`'s own docstring for the same
distinction the component's README documents: "these import `app.models`,
so they are block app code, never part of the vendored component"). The
weekly freshness audit does not touch this file.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security.auth import (
    PasswordService,
    RefreshRecord,
    TokenService,
    UserRecord,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User


def _user_to_record(user: User) -> UserRecord:
    """`roles` is stored as a JSON list (`app/models/user.py`) but the
    core's `UserRecord.roles` is a `tuple[str, ...]` — converted here at
    the store boundary, not inside the model, so `User.roles` stays a
    plain JSON-native `list` (what the `JSON` column type round-trips)."""
    return UserRecord(id=str(user.id), email=user.email, password_hash=user.password_hash, roles=tuple(user.roles))


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalizes a datetime read back from the DB to timezone-AWARE UTC.

    sqlite (this app's hermetic test dialect, `aiosqlite`) has no native
    timezone-aware datetime type — SQLAlchemy's `DateTime(timezone=True)`
    columns (`RefreshToken.issued_at`/`expires_at`/`used_at`) round-trip
    correctly on PostgreSQL (a real `timestamptz` column, always tz-aware
    coming back), but on sqlite the value comes back NAIVE regardless of
    what was written. `_core.AuthService.refresh` compares `row.
    expires_at <= self._now()`, and `self._now()` is always tz-aware (per
    `TokenService`/`AuthService`'s own documented `now` contract) —
    comparing an aware and a naive `datetime` raises `TypeError` at that
    comparison, not a silently-wrong result, so this normalization is
    required for correctness under sqlite, not just cosmetic. Every
    datetime this store EVER writes is UTC to begin with (`_core.py`'s
    `TokenService`/`AuthService` only ever construct `now()` as UTC-aware
    — see their own docstrings), so re-attaching `timezone.utc` to a value
    that came back naive is recovering known-lost information, not
    guessing: sqlite dropped the offset, it never had a different one."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _refresh_to_record(row: RefreshToken) -> RefreshRecord:
    return RefreshRecord(
        token_hash=row.token_hash,
        jti=row.jti,
        family_id=row.family_id,
        user_id=str(row.user_id),
        issued_at=_as_utc(row.issued_at),
        expires_at=_as_utc(row.expires_at),
        used_at=_as_utc(row.used_at),
        revoked=row.revoked,
    )


class SqlAlchemyUserStore:
    """Implements `_core.UserStore` against `app/models/user.py`'s `User`
    and this request's `AsyncSession`. Does NOT commit — matches
    `db-session/`'s `get_db()` session-per-request commit/rollback
    boundary (see that module's docstring); this store only flushes so a
    caller within the same request sees consistent (DB-generated id/
    timestamps) state. A concurrent duplicate-email registration race is
    still caught: `users.email`'s DB-level UNIQUE index (Alembic 0002)
    raises `IntegrityError` on the `INSERT` regardless of what
    `get_by_email`'s prior read saw."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # SECURITY (soft-delete auth bypass fix): both lookups below
    # deliberately honor soft-delete, matching `AsyncRepository._base_select`'s
    # own default (`include_deleted=False`) -- the rest of this app already
    # treats `deleted_at IS NOT NULL` as "gone", and these two auth lookups
    # are the ONLY reads of `User` that bypass `AsyncRepository` entirely
    # (they're constructed directly against `select(User)`, per this
    # store's own class docstring), so they must apply `User.not_deleted()`
    # by hand rather than inherit it for free. Without this, deactivating a
    # user (soft-deleting their row) would NOT revoke their ability to log
    # in (`get_by_email`, via `AuthService.login`) or to refresh
    # (`get_by_id`, via `AuthService.refresh` step 6) -- auth would fail
    # OPEN on deactivation instead of closed.
    #
    # NOTE (do NOT try to "fix"): an already-issued, not-yet-expired
    # *access* token remains valid until its own expiry even after this
    # change, because access tokens are stateless JWTs --
    # `AuthService.resolve_access` only decodes and verifies the token's
    # own signature/claims, it never re-checks the store. This is standard
    # JWT behavior, bounded by the short-lived `jwt_access_ttl_seconds`
    # (900s default) -- refresh denial (this fix) is what actually stops
    # session continuation past that point; there is no way to revoke a
    # single already-minted access token early without turning it into a
    # stateful token (out of scope here).
    async def get_by_email(self, email: str) -> UserRecord | None:
        result = await self._session.execute(select(User).where(User.email == email, User.not_deleted()))
        user = result.scalar_one_or_none()
        return _user_to_record(user) if user is not None else None

    async def get_by_id(self, id: str) -> UserRecord | None:
        try:
            user_id = uuid.UUID(id)
        except ValueError:
            # A malformed `sub` claim (not a UUID) cannot possibly match a
            # real row -- treated as "not found", not a crash, matching
            # `_core.AuthService.refresh`'s own "user gone -> InvalidToken"
            # handling of a genuinely-missing row.
            return None
        # Was `self._session.get(User, user_id)` -- a bare PK fetch that
        # bypasses soft-delete entirely (`Session.get` has no filtering
        # concept). Replaced with an explicit `select()` + `not_deleted()`
        # so a soft-deleted user's id resolves to "not found" here too,
        # same as `get_by_email` above -- `AuthService.refresh` step 6
        # then raises `InvalidToken`, consistent with its existing "user
        # gone" handling of a genuinely-missing row.
        result = await self._session.execute(select(User).where(User.id == user_id, User.not_deleted()))
        user = result.scalar_one_or_none()
        return _user_to_record(user) if user is not None else None

    async def create(self, email: str, password_hash: str, roles: Sequence[str]) -> UserRecord:
        user = User(email=email, password_hash=password_hash, roles=list(roles))
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return _user_to_record(user)


class SqlAlchemyRefreshTokenStore:
    """Implements `_core.RefreshTokenStore` against
    `app/models/refresh_token.py`'s `RefreshToken` and this request's
    `AsyncSession`.

    **`add`/`mark_used`/`revoke_family` each explicitly `commit()`** —
    NOT just `flush()` — per `_core.RefreshTokenStore`'s own protocol
    docstring: "Implementations MUST make add/mark_used/revoke_family
    durable (committed) before returning... so a concurrent second
    presentation of the just-rotated token sees the updated `used_at` and
    is correctly flagged as reuse rather than racing past this
    implementation's own write." A `flush()` alone only makes a change
    visible to the query planner WITHIN this same DB transaction — under
    the default READ COMMITTED isolation a concurrent transaction (a
    second, racing HTTP request reusing the same refresh token) would
    still see the pre-flush `used_at IS NULL` state until this session
    actually commits, defeating reuse detection under a genuine race. This
    intentionally commits mid-request, ahead of `get_db()`'s own
    end-of-request commit (see that dependency's docstring) — a second
    `commit()` on an already-clean session is a harmless no-op, so this
    does not conflict with that contract, only makes these three writes
    durable strictly earlier than it otherwise would."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: RefreshRecord) -> None:
        row = RefreshToken(
            token_hash=record.token_hash,
            jti=record.jti,
            family_id=record.family_id,
            user_id=uuid.UUID(record.user_id),
            issued_at=record.issued_at,
            expires_at=record.expires_at,
            used_at=record.used_at,
            revoked=record.revoked,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.commit()

    async def get_by_hash(self, token_hash: str) -> RefreshRecord | None:
        result = await self._session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        row = result.scalar_one_or_none()
        return _refresh_to_record(row) if row is not None else None

    async def mark_used(self, token_hash: str, used_at: datetime) -> None:
        result = await self._session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        row = result.scalar_one_or_none()
        if row is None:
            # _core.AuthService.refresh only calls mark_used() on a row it
            # just looked up successfully in the same call -- a None here
            # would mean it vanished mid-request (not expected in
            # practice). Silently returning (rather than raising) keeps
            # this store's contract "best-effort write", matching
            # RefreshTokenStore's Protocol, which declares no error path.
            return
        row.used_at = used_at
        await self._session.flush()
        await self._session.commit()

    async def revoke_family(self, family_id: str) -> None:
        result = await self._session.execute(select(RefreshToken).where(RefreshToken.family_id == family_id))
        rows = result.scalars().all()
        for row in rows:
            row.revoked = True
        await self._session.flush()
        await self._session.commit()


def utc_now() -> datetime:
    """The single `now` callable this app passes to BOTH `TokenService`
    and `AuthService` (see `_core.AuthService.__init__`'s own docstring:
    "a caller normally passes the SAME callable to both") — a plain
    module-level function rather than an inline lambda at each call site,
    so `app/api/deps.py:get_auth_service` and `get_token_service` below
    are provably passing the identical behavior, not two separately
    written (and possibly silently drifting) `lambda: datetime.now(...)`
    expressions."""
    return datetime.now(timezone.utc)


class AuthNotConfiguredError(RuntimeError):
    """Raised when `Settings.jwt_signing_key` is unset at the exact point
    auth is actually used (inside `get_token_service`, called from a
    per-request dependency) rather than at `Settings()` construction time
    (see `app/core/config.py`'s `jwt_signing_key` field docstring on why
    it resolves to `None`, not a hard failure, when unset — most of this
    app's routes/tests never touch auth at all). Deliberately a plain
    `RuntimeError` subclass, not part of `_core.AuthError`'s hierarchy —
    this is a SERVER misconfiguration, not a client-caused auth failure,
    so it must NOT be caught by `AUTH_ERROR_HTTP`/an `AppError` mapping
    and rendered as a 401/409; left unhandled, it reaches app/main.py's
    catch-all `Exception` handler and renders the generic `internal_error`
    envelope at 500 — "fail closed" without ever constructing a
    `TokenService` with an empty/absent signing key (which `TokenService.
    __init__` itself also refuses, per `_core.py`'s own `ValueError`
    guard — this is the layer above that, for the `None`-vs-empty-string
    case `TokenService` cannot see because it's never even called)."""


@lru_cache
def get_password_service() -> PasswordService:
    """One process-wide `PasswordService` — see that class's own docstring
    on why: its `dummy_verify()` timing defense depends on a precomputed
    throwaway hash computed ONCE at construction (a real Argon2id hash,
    not a cheap operation) so every login's "email not found" path costs
    the same wall-clock time as a real `verify()` call; constructing a
    fresh instance per request would pay that Argon2id cost on every
    single request, not just once at process start."""
    return PasswordService()


def get_token_service(settings: Settings) -> TokenService:
    """Builds a `TokenService` from this project's `Settings` — cheap to
    construct (holds config values only, no heavy crypto in `__init__`,
    unlike `PasswordService` above), so a fresh instance per request is
    fine and keeps this function trivially pure over its `settings`
    argument rather than needing its own cache-invalidation story if
    settings ever change between requests (as the test suite's
    `make_client` fixture does, per-test).

    Raises `AuthNotConfiguredError` if `settings.jwt_signing_key` is
    `None` — see that exception's own docstring for the fail-closed
    rationale."""
    if not settings.jwt_signing_key:
        raise AuthNotConfiguredError(
            "JWT_SIGNING_KEY is not configured. Set the JWT_SIGNING_KEY environment "
            "variable (or its AWS Secrets Manager equivalent -- see "
            "app/core/security/secret_store's get_secret()) before any auth endpoint "
            "is used."
        )
    return TokenService(
        settings.jwt_signing_key,
        issuer=settings.jwt_issuer,
        access_ttl=timedelta(seconds=settings.jwt_access_ttl_seconds),
        refresh_ttl=timedelta(seconds=settings.jwt_refresh_ttl_seconds),
        now=utc_now,
    )
