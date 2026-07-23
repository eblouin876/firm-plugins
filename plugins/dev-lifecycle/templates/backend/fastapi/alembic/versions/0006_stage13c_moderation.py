"""Stage 13c: moderation -- flags

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

Adds `flags` (`app/models/flag.py`) column-for-column, written by hand
rather than via `alembic revision --autogenerate` (no live DB was used to
generate this file, matching 0001-0005's own convention).

`flags.reporter_id` is the ONE FK in this migration with an explicit
non-default `ondelete` (`SET NULL`) -- every other FK in this catalog
(`blog_posts.author_id`, `blog_comments.{post_id,author_id}`) is left at
the DB-level default (RESTRICT) -- see `app/models/flag.py`'s own
docstring for why a flag's own audit value outlives its reporter's
account. `flags.resolved_by_id` IS left at that RESTRICT default, matching
every other "don't silently cascade away an audit trail" FK in this
catalog. `flags.target_id` carries NO ForeignKeyConstraint at all --
deliberately polymorphic, see that column's own docstring on the model.

Indexes: `flags.status` + `flags.target_type` (individually, plus one
composite `ix_flags_status_target_type` covering the admin queue's own
`?status=&target_type=` filter shape), `flags.{target_id,reporter_id,
resolved_by_id}` -- the plan's own "index on status + target_type + the FK
cols" requirement."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flags",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=False),
        sa.Column("reporter_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolved_by_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["users.id"], name="fk_flags_reporter_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], name="fk_flags_resolved_by_id_users"),
    )
    op.create_index("ix_flags_target_type", "flags", ["target_type"], unique=False)
    op.create_index("ix_flags_target_id", "flags", ["target_id"], unique=False)
    op.create_index("ix_flags_reporter_id", "flags", ["reporter_id"], unique=False)
    op.create_index("ix_flags_status", "flags", ["status"], unique=False)
    op.create_index("ix_flags_resolved_by_id", "flags", ["resolved_by_id"], unique=False)
    op.create_index("ix_flags_status_target_type", "flags", ["status", "target_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_flags_status_target_type", table_name="flags")
    op.drop_index("ix_flags_resolved_by_id", table_name="flags")
    op.drop_index("ix_flags_status", table_name="flags")
    op.drop_index("ix_flags_reporter_id", table_name="flags")
    op.drop_index("ix_flags_target_id", table_name="flags")
    op.drop_index("ix_flags_target_type", table_name="flags")
    op.drop_table("flags")
