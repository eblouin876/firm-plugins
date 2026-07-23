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
