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


def downgrade() -> None:
    op.drop_table("items")
