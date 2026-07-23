"""The contract exemplar model: a minimal `Item` matching backend/fastapi's
`app/models/item.py` field-for-field (`id` UUID primary key, `created_at`/
`updated_at`, soft-delete via `deleted_at`, `name`/`description`) so this
block's eventual DRF serializer round-trips the same wire shape the FastAPI
block's Pydantic schemas already produce. Not a vendored file — this is this
step's own app code, the Django-ORM counterpart to
`templates/components/backend/db-mixins/mixins.py` (that component's own
module docstring: "a Django backend (Stage 4) does NOT reuse this file; it
reaches for Django's own `models.UUIDField`, `auto_now_add`/`auto_now`, and
a custom soft-delete manager instead" — this module is that reach)."""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q


class ItemQuerySet(models.QuerySet):
    """The queryset-level soft-delete filter — `Item.objects` (below) is
    built on this via `.as_manager()` so every default lookup
    (`Item.objects.all()`, `.get()`, `.filter()`) already excludes
    soft-deleted rows without a caller having to remember to add
    `deleted_at__isnull=True` themselves. Mirrors
    `db-mixins/mixins.py`'s `SoftDeleteMixin.not_deleted()` — the
    SQLAlchemy repository composes that as a `WHERE` fragment on every
    `select()`; this queryset is the Django-ORM equivalent default-scoping
    mechanism."""

    def not_deleted(self) -> "ItemQuerySet":
        return self.filter(deleted_at__isnull=True)

    def with_deleted(self) -> "ItemQuerySet":
        """Escape hatch for the rare caller (an admin view, a hard-delete
        cleanup job) that genuinely needs soft-deleted rows too — the
        default manager below never returns them."""
        return self


class ItemManager(models.Manager.from_queryset(ItemQuerySet)):
    """`Item.objects`'s default manager: every `Item.objects.<lookup>()`
    call is scoped through `ItemQuerySet.not_deleted()` first (`get_queryset`
    override below), the same "soft-deleted rows are invisible by default"
    posture `db-mixins/mixins.py`'s `SoftDeleteMixin` establishes for the
    SQLAlchemy block. Use `Item.objects.with_deleted()` (via
    `ItemQuerySet.with_deleted`) to opt out for the rare caller that needs
    everything."""

    def get_queryset(self) -> ItemQuerySet:
        return super().get_queryset().not_deleted()


class Item(models.Model):
    """Field-for-field match to backend/fastapi's `Item`
    (`UUIDPrimaryKey` + `TimestampMixin` + `SoftDeleteMixin` composed):
    `id` (UUID, default `uuid4`), `created_at` (set once, on insert),
    `updated_at` (bumped on every Django-ORM `.save()`), `deleted_at`
    (nullable — `NULL` means "not deleted"), `name`/`description`. See
    that model's own module docstring for the SQLAlchemy-side contract this
    mirrors.

    `objects` is `ItemManager` (soft-delete-scoped by default, see above);
    `all_objects` is the unscoped default `models.Manager()`, kept around
    for the same "escape hatch" reason `ItemQuerySet.with_deleted()`
    exists — Django recommends keeping an unfiltered manager available even
    when a custom default manager narrows `objects` (see Django's own
    "Custom managers and model inheritance" docs), since some internal
    machinery (e.g. `Model.objects.get_or_create` from a migration, an
    admin registration) expects an unscoped default manager to exist
    somewhere on the model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=2000, null=True, blank=True)

    objects = ItemManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "items"
        indexes = [
            # Partial index on deleted_at WHERE NULL — Postgres-specific
            # (Django compiles a no-op / full index on backends without
            # partial-index support, e.g. sqlite in the hermetic test
            # settings; harmless there, just not partial). Speeds up the
            # default manager's `deleted_at IS NULL` filter on every
            # unscoped lookup without indexing the (much rarer) soft-
            # deleted rows too. Mirrors `db-mixins/mixins.py`'s
            # `SoftDeleteMixin.not_deleted()` WHERE fragment being the
            # thing every default query filters on.
            models.Index(
                fields=["deleted_at"],
                name="items_not_deleted_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_deleted(self, *, when=None) -> None:
        """Python-side soft-delete mutation, mirroring
        `SoftDeleteMixin.mark_deleted()`'s API — sets `deleted_at` without
        saving; the caller decides when to `.save(update_fields=[...])`."""
        from django.utils import timezone

        self.deleted_at = when or timezone.now()


# ---------------------------------------------------------------------------
# Stage 5b (#44): auth tables -- the User/RefreshToken the vendored auth
# component's UserStore/RefreshTokenStore protocols
# (core/security/auth/_core.py) are implemented against (see
# core/security/auth/stores.py, Step 6). Column-for-column match to
# backend/fastapi's app/models/{user,refresh_token}.py, cross-checked
# against alembic/versions/0002_create_auth_tables.py -- see each model's
# own docstring for the exact shape mirrored and any intentional nuance.
# Not vendored files -- this block's own app code, same as Item above.
# ---------------------------------------------------------------------------


class UserQuerySet(models.QuerySet):
    """`User`'s soft-delete filter -- identical shape to `ItemQuerySet`
    above; see that class's own docstring. Composed by `UserManager`
    (below) into `User.objects`'s default, soft-delete-scoped queryset."""

    def not_deleted(self) -> "UserQuerySet":
        return self.filter(deleted_at__isnull=True)

    def with_deleted(self) -> "UserQuerySet":
        """Escape hatch — see `ItemQuerySet.with_deleted`'s own docstring.
        This is also the SECURITY-relevant queryset a raw, unscoped lookup
        would need to bypass `User.objects`'s default filtering; the
        vendored auth component's own store (`core/security/auth/
        stores.py`) deliberately never uses it — see that module's own
        "soft-delete auth-bypass fix" docstring on why its lookups always
        go through the soft-delete-scoped default manager instead."""
        return self


class UserManager(models.Manager.from_queryset(UserQuerySet)):
    """`User.objects`'s default manager — identical shape to `ItemManager`
    above; see that class's own docstring. `User.objects.with_deleted()` is
    the same opt-out escape hatch `Item.objects.with_deleted()` provides."""

    def get_queryset(self) -> UserQuerySet:
        return super().get_queryset().not_deleted()


class User(models.Model):
    """The `User` the vendored auth component's `UserStore` protocol
    (`core/security/auth/_core.py`) is implemented against (see
    `core/security/auth/stores.py`, Step 6) — column-for-column match to
    `backend/fastapi`'s `app/models/user.py` `User`
    (`UUIDPrimaryKey` + `TimestampMixin` + `SoftDeleteMixin` composed
    there) and `alembic/versions/0002_create_auth_tables.py`'s `users`
    table: `id` (UUID, default `uuid4`), `email` (unique, 320 chars —
    RFC 5321's own max mailbox-address length), `password_hash` (255
    chars — an Argon2id encoded hash string never approaches this, but
    it's the same generous bound the FastAPI model uses), `roles`
    (JSON, not Postgres `ARRAY` — see below), `created_at`/`updated_at`
    (Django `auto_now_add`/`auto_now`, the ORM-level equivalent of the
    SQLAlchemy model's `server_default=func.now()`/`onupdate=func.now()`),
    `deleted_at` (nullable — `NULL` means "not deleted").

    `email` is stored already-normalized (lowercased/stripped) by
    `_core.AuthService._normalize_email` — this model does not re-normalize
    it, so the unique constraint below is on exactly the value the auth
    core already normalized, matching `app/models/user.py`'s own docstring
    on the same point.

    `roles` uses `models.JSONField` (cross-dialect JSON, not a Postgres-only
    `ArrayField`) — deliberately, even though this table only ever runs on
    Postgres in prod: this app's hermetic test suite
    (`config/settings_test.py`) runs the identical model against sqlite3,
    and `ArrayField` has no sqlite equivalent. This is the SAME JSON-not-
    ARRAY choice `app/models/user.py`'s own docstring documents for the
    SQLAlchemy side — the one INTENTIONAL parity nuance this model shares
    with that reference (Postgres could use a native `ARRAY(varchar)`
    column instead; both tracks deliberately don't, for hermetic-testability
    reasons that apply equally to both ORMs). `default=list`, not `[]` — a
    callable default, not a single shared mutable one; see
    `app/models/user.py`'s own docstring for the identical mutable-default
    footgun this avoids.

    Deliberately a plain `User(models.Model)` — NOT `settings.
    AUTH_USER_MODEL`, NOT `AbstractBaseUser`, and this app registers no
    Django admin for it. This app's entire authentication surface is the
    vendored auth component's own JWT-based `AuthService`
    (`core/security/auth/_core.py`) — `AbstractBaseUser` exists to support
    Django's OWN session-cookie auth, password-reset tokens, and
    permission/group machinery, none of which this app uses; adopting it
    would pull in an entire parallel, unused authentication system purely
    for the field names it happens to also define.

    `objects` is `UserManager` (soft-delete-scoped by default — see
    `UserQuerySet` above); `all_objects` is the unscoped default
    `models.Manager()`, the same escape hatch `Item.all_objects` provides,
    kept for the same "some internal machinery expects an unscoped default
    manager to exist somewhere on the model" reason `Item`'s own docstring
    cites."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.CharField(max_length=320, unique=True)
    password_hash = models.CharField(max_length=255)
    roles = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    objects = UserManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "users"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.email

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_deleted(self, *, when=None) -> None:
        """Python-side soft-delete mutation — see `Item.mark_deleted`'s own
        docstring; the SECURITY-relevant consequence for `User` specifically
        is documented on `core/security/auth/stores.py`'s
        `DjangoUserStore.get_by_email`/`get_by_id` (a deactivated/soft-
        deleted user fails login and refresh, closed)."""
        from django.utils import timezone

        self.deleted_at = when or timezone.now()


class RefreshToken(models.Model):
    """One row per minted refresh token — the `RefreshToken` the vendored
    auth component's `RefreshTokenStore` protocol
    (`core/security/auth/_core.py`) is implemented against (see
    `core/security/auth/stores.py`, Step 6), persisted exactly as
    `_core.RefreshRecord` describes: `token_hash` (never the raw token —
    see `_core.hash_token`'s own docstring) is the lookup key, `used_at`/
    `revoked` implement the rotation-with-reuse-detection state machine
    (`_core.AuthService.refresh`'s docstring is THE reference for what this
    table's rows mean at each state).

    Deliberately composes plain `models.Model`, NOT `User`'s soft-delete
    manager above — a refresh-token row is never "soft deleted"; its
    lifecycle is fully captured by `used_at`/`revoked` already (see
    `_core.RefreshRecord`'s own docstring on why a used row is RETAINED,
    not deleted, soft or otherwise) — matching `app/models/refresh_token.py`
    composing `UUIDPrimaryKey` + `TimestampMixin` only, never
    `SoftDeleteMixin`.

    Column-for-column match to `backend/fastapi`'s
    `app/models/refresh_token.py` `RefreshToken` and
    `alembic/versions/0002_create_auth_tables.py`'s `refresh_tokens` table,
    with TWO INTENTIONAL parity nuances:

    1. **`user` uses `on_delete=models.PROTECT` — an app-level (Django ORM)
       enforcement — vs. Alembic 0002's DB-level `ForeignKeyConstraint`
       left at its default `ondelete` (RESTRICT).** Both refuse to delete a
       `User` row that still has `RefreshToken` rows pointing at it —
       `PROTECT` raises `django.db.models.ProtectedError` INSIDE the ORM,
       before any `DELETE` statement reaches the database, while RESTRICT
       is enforced by Postgres itself at the SQL level (would surface as an
       `IntegrityError` instead). Neither this app nor `backend/fastapi`
       ever hard-deletes a `User` row today (both use `User`'s soft-delete
       instead — see `User.mark_deleted` above), so this divergence isn't
       exercised in practice; `PROTECT` is still the correct Django-ORM
       expression of the same "don't silently lose a security-relevant
       audit trail of past sessions" intent `0002_create_auth_tables.py`'s
       own module docstring gives for choosing RESTRICT over CASCADE.
    2. **No `created_at`/`updated_at` columns**, unlike Alembic 0002's
       `refresh_tokens` table (which carries them via
       `app/models/refresh_token.py`'s `TimestampMixin`). Omitted
       deliberately, not an oversight: this app's stores
       (`core/security/auth/stores.py`, per this block's locked "stores use
       Django's ASYNC ORM" decision) write `mark_used`/`revoke_family` via
       a queryset-level `.filter(...).aupdate(...)` call, and Django's
       `auto_now` only fires on `Model.save()` — a queryset `.update()`/
       `.aupdate()` bypasses model-level field machinery entirely, so an
       `updated_at` column here would silently go stale on every write
       instead of reflecting reality. Leaving the column out is more honest
       than shipping a timestamp that lies. `issued_at` already carries
       this row's creation time for the table's actual purpose (rotation
       auditing), so nothing this table's own consumers need is lost."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # UNIQUE — the lookup key `RefreshTokenStore.get_by_hash` queries by
    # (SHA-256 hex digest of the raw token, per `_core.hash_token`).
    token_hash = models.CharField(max_length=64, unique=True)
    jti = models.CharField(max_length=32)
    # INDEXED (not unique) — `RefreshTokenStore.revoke_family` queries every
    # row sharing one `family_id` at once (reuse detection, logout).
    family_id = models.CharField(max_length=32, db_index=True)
    # PROTECT, not CASCADE — see this class's own docstring, nuance 1.
    user = models.ForeignKey(User, on_delete=models.PROTECT, db_index=True)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True, default=None)
    revoked = models.BooleanField(default=False)

    class Meta:
        db_table = "refresh_tokens"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"RefreshToken(jti={self.jti})"
