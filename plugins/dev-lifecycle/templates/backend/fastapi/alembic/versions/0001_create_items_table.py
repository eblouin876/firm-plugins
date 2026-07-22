"""create items table

Revision ID: 0001
Revises:
Create Date: 2026-07-22

Matches app/models/item.py's `Item` (UUIDPrimaryKey + TimestampMixin +
SoftDeleteMixin) column-for-column, written by hand rather than via
`alembic revision --autogenerate` (no live DB was used to generate this
file, per the offline-emittable requirement) — see README.md's Alembic
section for the verification transcript this migration was proved against
(both `--sql` offline emission and a real online run against Postgres 16).

Stage 3 #26, Step 3a: added `ix_items_deleted_at_null`, a PARTIAL index on
`deleted_at WHERE deleted_at IS NULL` — every not-deleted list/get query
(`AsyncRepository`'s default `include_deleted=False`, via
`SoftDeleteMixin.not_deleted()`) filters on exactly that predicate, so a
partial index covering only live rows is smaller and cheaper to maintain
than a full index that also carries every soft-deleted row. Postgres
supports partial indexes natively (`postgresql_where=`); sqlite's
`CREATE INDEX` (what SQLAlchemy/Alembic emits for the hermetic aiosqlite
tests) accepts the same `WHERE` clause syntax too, so this is not a
Postgres-only construct here, but `postgresql_where=` is what makes the
*intent* (a Postgres partial index) explicit and dialect-scoped rather
than relying on sqlite happening to accept the same syntax.

TODO(templates/components/backend/db-mixins): the `SoftDeleteMixin`
component itself (mixins.py) should document/carry this same partial-index
pattern as guidance for any project composing it with an index on
`deleted_at` — not changed here; this migration only applies the pattern
to the `items` exemplar table, per this issue's scope (do not edit the
db-mixins source component in this step).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index on Postgres (WHERE deleted_at IS NULL — see module
    # docstring); on sqlite (hermetic tests) `postgresql_where` is a no-op
    # dialect kwarg and this still emits a valid plain index.
    op.create_index(
        "ix_items_deleted_at_null",
        "items",
        ["deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_items_deleted_at_null", table_name="items")
    op.drop_table("items")
