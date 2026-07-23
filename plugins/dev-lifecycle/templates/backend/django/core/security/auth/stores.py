"""App-specific Django-ORM-backed implementations of the vendored auth
component's `UserStore`/`RefreshTokenStore` protocols (`_core.py`), plus
the app-level `PasswordService`/`TokenService`/`AuthService` construction
Agent B's views call via `build_auth_service()`.

**NOT a vendored file** — it lives alongside `_core.py`/`django.py`/
`__init__.py` in this directory because that is where this app's auth
wiring naturally sits, but it imports `core.models` and
`django.conf.settings`, so it is ordinary app code (see `__init__.py`'s own
docstring for the same distinction the component's README documents:
"these import `core.models`, so they are block app code, never part of the
vendored component"). The weekly freshness audit does not touch this file.

**Async ORM only, never bare sync ORM.** Every store method below uses
Django's async QuerySet API (`.afirst()`, `.acreate()`, `.filter(...).
aupdate(...)`) — this block's locked "stores use Django's ASYNC ORM"
decision. A bare sync ORM call (`.first()`, `.create()`, plain
`.filter(...).update(...)`) executed from inside the async context these
methods run in would raise `SynchronousOnlyOperation` — Django's async ORM
support does not silently fall back to a thread-pool bridge the way, say,
`sync_to_async`-wrapped code does; it refuses outright. Agent B's views
bridge the other direction (an ordinary DRF sync view calling into this
async `AuthService`) via `asgiref.sync.async_to_sync`, not by making these
stores sync.

Reference implementation this file's shape mirrors: `backend/fastapi`'s
`app/core/security/auth/stores.py` (SQLAlchemy `AsyncSession`-backed) — see
each class/function below for exactly what carries over unchanged and what
differs because Django's async ORM has no session object to hold.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from django.conf import settings

from core.models import RefreshToken, User
from core.security.auth import AuthService, PasswordService, RefreshRecord, TokenService, UserRecord


def _user_to_record(user: User) -> UserRecord:
    """`roles` is stored as a JSON list (`core/models.py`'s `User.roles`)
    but the core's `UserRecord.roles` is a `tuple[str, ...]` — converted
    here at the store boundary, not inside the model, so `User.roles` stays
    a plain JSON-native `list` (what `models.JSONField` round-trips).
    Identical conversion to `app/core/security/auth/stores.py`'s own
    `_user_to_record`."""
    return UserRecord(id=str(user.id), email=user.email, password_hash=user.password_hash, roles=tuple(user.roles))


def _refresh_to_record(row: RefreshToken) -> RefreshRecord:
    """No `_as_utc`-style normalization needed here — see `utc_now`'s own
    docstring below for why Django's `USE_TZ=True` makes that FastAPI-side
    naive-sqlite workaround unnecessary on this track."""
    return RefreshRecord(
        token_hash=row.token_hash,
        jti=row.jti,
        family_id=row.family_id,
        user_id=str(row.user_id),
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
        revoked=row.revoked,
    )


class DjangoUserStore:
    """Implements `_core.UserStore` against `core.models.User` via Django's
    async ORM. No session/connection object to hold, unlike
    `SqlAlchemyUserStore`'s `AsyncSession` constructor argument — Django's
    ORM manages the per-task async database connection itself, so this
    class needs no `__init__` at all; every method below is a plain
    manager/queryset call.

    A concurrent duplicate-email registration race is still caught:
    `core.models.User.email`'s DB-level `unique=True` constraint (see
    `core/migrations/0002_user_refreshtoken.py`) raises
    `django.db.utils.IntegrityError` on the `INSERT` regardless of what
    `get_by_email`'s prior read saw — `AuthService.register`'s own
    `get_by_email`-then-`create` sequence is the friendly-error path, this
    constraint is the enforcement of last resort, the identical two-layer
    posture `SqlAlchemyUserStore`'s own docstring documents."""

    # SECURITY (soft-delete auth-bypass fix, carried over from Stage 5a):
    # both lookups below query through `User.objects` -- `UserManager`
    # (core/models.py), NOT `User.all_objects` -- and `User.objects`'s own
    # `get_queryset()` override already applies `UserQuerySet.not_deleted()`
    # to EVERY lookup by default, so `.filter(email=...)`/`.filter(id=...)`
    # below inherit that scoping automatically, with no explicit
    # `deleted_at__isnull=True` needed at each call site (unlike
    # `SqlAlchemyUserStore`, which must add `User.not_deleted()` to each
    # `select()` by hand, since `AsyncRepository`'s own default scoping is
    # bypassed entirely by that store's direct `select(User)` construction —
    # see that class's own docstring). The SECURITY property is identical
    # either way: deactivating a user (soft-deleting their row) revokes
    # their ability to log in (`get_by_email`, via `AuthService.login`) and
    # to refresh (`get_by_id`, via `AuthService.refresh` step 6) — auth
    # fails CLOSED on deactivation, not open.
    #
    # NOTE (do NOT try to "fix"): an already-issued, not-yet-expired
    # *access* token remains valid until its own expiry even after
    # deactivation, because access tokens are stateless JWTs --
    # `AuthService.resolve_access` only decodes and verifies the token's
    # own signature/claims, it never re-checks the store. This is standard
    # JWT behavior, bounded by the short-lived `JWT_ACCESS_TTL_SECONDS`
    # (900s default) -- refresh denial (this fix) is what actually stops
    # session continuation past that point; there is no way to revoke a
    # single already-minted access token early without turning it into a
    # stateful token (out of scope here). Identical caveat to
    # `SqlAlchemyUserStore`'s own.
    async def get_by_email(self, email: str) -> UserRecord | None:
        user = await User.objects.filter(email=email).afirst()
        return _user_to_record(user) if user is not None else None

    async def get_by_id(self, id: str) -> UserRecord | None:
        try:
            user_id = uuid.UUID(id)
        except ValueError:
            # A malformed `sub` claim (not a UUID) cannot possibly match a
            # real row -- treated as "not found", not a crash, matching
            # `_core.AuthService.refresh`'s own "user gone -> InvalidToken"
            # handling of a genuinely-missing row. Identical to
            # `SqlAlchemyUserStore.get_by_id`'s own guard.
            return None
        user = await User.objects.filter(id=user_id).afirst()
        return _user_to_record(user) if user is not None else None

    async def create(self, email: str, password_hash: str, roles: Sequence[str]) -> UserRecord:
        user = await User.objects.acreate(email=email, password_hash=password_hash, roles=list(roles))
        return _user_to_record(user)


class DjangoRefreshTokenStore:
    """Implements `_core.RefreshTokenStore` against
    `core.models.RefreshToken` via Django's async ORM.

    **Durability = Django's own AUTOCOMMIT, not an explicit `commit()`
    call.** `SqlAlchemyRefreshTokenStore` (backend/fastapi) must call
    `session.commit()` explicitly after each write because SQLAlchemy's
    `AsyncSession` holds a session-scoped transaction that only `flush()`es
    (makes a change visible to later queries WITHIN that same transaction)
    by default — a `flush()` alone would not be durable against a
    concurrent, separately-connected transaction until an explicit
    `commit()` follows. Django has no equivalent session-held transaction
    to manage here: this block's locked posture is `ATOMIC_REQUESTS` left
    unset (see `config/settings.py`) and NO `transaction.atomic()` block
    anywhere around these calls (this block's own locked decision) — under
    that posture, every one of Django's async ORM write calls
    (`.acreate()`, `.filter(...).aupdate(...)`) is its OWN single
    autocommitted SQL statement, durable the instant the call returns, with
    nothing further to flush or commit. That is EXACTLY the durability
    `_core.RefreshTokenStore`'s own Protocol docstring requires:
    "Implementations MUST make `add`/`mark_used`/`revoke_family` durable
    (committed) before returning... so a concurrent second presentation of
    the just-rotated token sees the updated `used_at` and is correctly
    flagged as reuse rather than racing past this implementation's own
    write" — it falls out of Django's default autocommit mode for free,
    PROVIDED nothing wraps these calls in `transaction.atomic()` (which
    would defer the commit to the end of that block) or sets
    `ATOMIC_REQUESTS = True` (which would defer it to end-of-request,
    reintroducing exactly the race this Protocol forbids). `tests/
    test_auth_stores.py` uses `@pytest.mark.django_db(transaction=True)`
    specifically so this durability is genuinely exercised against real
    autocommit semantics, not pytest-django's own default (a wrapping
    `atomic()` block per test, rolled back at the end) — see that test
    module's own docstring.

    `add`/`mark_used`/`revoke_family` below deliberately do nothing beyond
    the single ORM call each needs — there is no `commit()` to call, unlike
    the SQLAlchemy reference."""

    async def add(self, record: RefreshRecord) -> None:
        await RefreshToken.objects.acreate(
            token_hash=record.token_hash,
            jti=record.jti,
            family_id=record.family_id,
            user_id=uuid.UUID(record.user_id),
            issued_at=record.issued_at,
            expires_at=record.expires_at,
            used_at=record.used_at,
            revoked=record.revoked,
        )

    async def get_by_hash(self, token_hash: str) -> RefreshRecord | None:
        row = await RefreshToken.objects.filter(token_hash=token_hash).afirst()
        return _refresh_to_record(row) if row is not None else None

    async def mark_used(self, token_hash: str, used_at: datetime) -> None:
        # `_core.AuthService.refresh` only calls `mark_used()` on a row it
        # just looked up successfully in the same call -- an empty
        # queryset here would mean it vanished mid-request (not expected in
        # practice). `.aupdate()` on a queryset matching zero rows silently
        # updates zero rows rather than raising, keeping this store's
        # contract "best-effort write", matching `RefreshTokenStore`'s
        # Protocol, which declares no error path -- identical posture to
        # `SqlAlchemyRefreshTokenStore.mark_used`'s own "row is None ->
        # silently return" handling, expressed here as a no-op update
        # instead of an explicit early return.
        await RefreshToken.objects.filter(token_hash=token_hash).aupdate(used_at=used_at)

    async def revoke_family(self, family_id: str) -> None:
        await RefreshToken.objects.filter(family_id=family_id).aupdate(revoked=True)


def utc_now() -> datetime:
    """The single `now` callable this app passes to BOTH `TokenService` and
    `AuthService` (see `_core.AuthService.__init__`'s own docstring: "a
    caller normally passes the SAME callable to both") — a plain
    module-level function, not an inline lambda at each call site, so
    `get_token_service` below and `build_auth_service` are provably passing
    the identical behavior. Identical shape to `app/core/security/auth/
    stores.py`'s own `utc_now`.

    **Deliberate simplification vs. the FastAPI reference: no `_as_utc`
    naive-sqlite patch-up needed here.** `SqlAlchemyRefreshTokenStore`'s
    reference implementation must re-attach `timezone.utc` to every
    datetime it reads back on sqlite (its hermetic test dialect), because
    raw aiosqlite has no native timezone-aware datetime type and always
    hands SQLAlchemy back a NAIVE value regardless of what was written.
    Django's ORM sits at a different layer: with `USE_TZ = True`
    (`config/settings.py`, this block's locked setting), Django's own
    `DateTimeField` performs the naive<->aware conversion ITSELF, uniformly
    across every backend it supports — sqlite (this block's hermetic test
    dialect, via ISO-format string storage) and Postgres (prod, via a real
    `timestamptz` column) both hand back tz-aware UTC `datetime` values from
    the ORM, with no per-backend special-casing needed at the call site.
    `_refresh_to_record` (above) therefore reads `row.issued_at`/
    `expires_at`/`used_at` directly with no normalization step — this is a
    genuine simplification this Django-track module gets for free, not an
    oversight or a gap relative to the FastAPI reference."""
    return datetime.now(timezone.utc)


class AuthNotConfiguredError(RuntimeError):
    """Raised when `settings.JWT_SIGNING_KEY` is unset at the exact point
    auth is actually used (inside `get_token_service`, called from
    `build_auth_service`, called from a view) rather than at Django
    settings-module import time (see `config/settings.py`'s
    `JWT_SIGNING_KEY` line — resolved via `secret_store.get_secret(...,
    required=False)`, so it's `None`, not a hard failure, when unset — most
    of this app's routes/tests never touch auth at all). Deliberately a
    plain `RuntimeError` subclass, NOT part of `_core.AuthError`'s
    hierarchy — this is a SERVER misconfiguration, not a client-caused auth
    failure, so it must NOT be caught by `AUTH_ERROR_HTTP`/an `AppError`-
    style mapping and rendered as a 401/409; left unhandled, it reaches
    `core.exceptions.exception_handler`'s catch-all `Exception` branch and
    renders the generic `internal_error` envelope at 500 — "fail closed"
    without ever constructing a `TokenService` with an empty/absent signing
    key (which `TokenService.__init__` itself also refuses, per `_core.py`'s
    own `ValueError` guard — this is the layer above that, for the
    `None`-vs-empty-string case `TokenService` cannot see because it's
    never even called). Identical shape and rationale to `app/core/
    security/auth/stores.py`'s own `AuthNotConfiguredError`."""


@lru_cache
def get_password_service() -> PasswordService:
    """One process-wide `PasswordService` — see that class's own docstring
    on why: its `dummy_verify()` timing defense depends on a precomputed
    throwaway hash computed ONCE at construction (a real Argon2id hash, not
    a cheap operation) so every login's "email not found" path costs the
    same wall-clock time as a real `verify()` call; constructing a fresh
    instance per request would pay that Argon2id cost on every single
    request, not just once at process start. Identical to `app/core/
    security/auth/stores.py`'s own `get_password_service`."""
    return PasswordService()


def get_token_service() -> TokenService:
    """Builds a `TokenService` from `django.conf.settings` directly —
    unlike the FastAPI reference's `get_token_service(settings: Settings)`,
    this takes NO argument: this block has no per-request `Settings`
    object to thread through (see `config/settings.py`'s own module
    docstring — this block reads `django.conf.settings`, Django's own
    global settings object, everywhere, rather than a pydantic `Settings`
    instance constructed per-app). Cheap to construct (holds config values
    only, no heavy crypto in `__init__`, unlike `PasswordService` above),
    so a fresh instance per call is fine.

    Raises `AuthNotConfiguredError` if `settings.JWT_SIGNING_KEY` is falsy
    (`None` or an empty string) — see that exception's own docstring for
    the fail-closed rationale."""
    if not settings.JWT_SIGNING_KEY:
        raise AuthNotConfiguredError(
            "JWT_SIGNING_KEY is not configured. Set the JWT_SIGNING_KEY environment "
            "variable (or its AWS Secrets Manager equivalent -- see "
            "core.contract.secret_store.get_secret()) before any auth endpoint is used."
        )
    return TokenService(
        settings.JWT_SIGNING_KEY,
        issuer=settings.JWT_ISSUER,
        access_ttl=timedelta(seconds=settings.JWT_ACCESS_TTL_SECONDS),
        refresh_ttl=timedelta(seconds=settings.JWT_REFRESH_TTL_SECONDS),
        now=utc_now,
    )


def build_auth_service() -> AuthService:
    """Constructs a fresh `AuthService`, wired to this module's
    Django-async-ORM-backed `DjangoUserStore`/`DjangoRefreshTokenStore`,
    the process-wide `get_password_service()`, and a `get_token_service()`
    built from the current `django.conf.settings`. This is what Agent B's
    views call — a DRF view (ordinarily synchronous) bridges into the
    returned `AuthService`'s async methods via `asgiref.sync.
    async_to_sync(...)`, the same bridge `tests/test_auth_stores.py` uses
    to exercise the stores below directly.

    No arguments, unlike `app/core/security/auth/stores.py`'s
    FastAPI-dependency-shaped `get_auth_service` (which takes an
    `AsyncSession` from `Depends(get_db)`) — Django's async ORM has no
    per-request session object for a caller to hand in; each store method
    manages its own database access per call. A fresh `AuthService` (and
    fresh stores) is constructed on every call rather than cached, since
    `DjangoUserStore`/`DjangoRefreshTokenStore` are stateless (no
    `__init__` at all) and `get_token_service()` is itself cheap — see that
    function's own docstring. Raises `AuthNotConfiguredError` (via
    `get_token_service()`) if `settings.JWT_SIGNING_KEY` is unset."""
    return AuthService(
        users=DjangoUserStore(),
        refresh_tokens=DjangoRefreshTokenStore(),
        passwords=get_password_service(),
        tokens=get_token_service(),
        now=utc_now,
    )
