"""create auth tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

Matches app/models/user.py's `User` (UUIDPrimaryKey + TimestampMixin +
SoftDeleteMixin) and app/models/refresh_token.py's `RefreshToken`
(UUIDPrimaryKey + TimestampMixin) column-for-column, written by hand rather
than via `alembic revision --autogenerate` (no live DB was used to
generate this file, per the offline-emittable requirement, matching
0001_create_items_table.py's own convention) — see README.md's Alembic
section for the verification transcript this migration was proved against
(both `--sql` offline emission and a real online run against Postgres 16).

Stage 5a (#41): `users.email` gets a UNIQUE index (`ix_users_email`) — the
auth core's `AuthService.register` checks `UserStore.get_by_email` before
inserting, but that read-then-write is not itself atomic against a
concurrent duplicate registration; the DB-level unique constraint is what
actually prevents two rows with the same normalized email under a race
(the app-level check is the friendly-error path; this index is the
enforcement of last resort, matching references/backend/sqlalchemy.md's
"Models" guidance to make constraints explicit at the DB level, same
rationale 0001's own module docstring cites for its partial index).
`refresh_tokens.token_hash` gets a UNIQUE index for the same reason (`add`
inserting a hash collision, astronomically unlikely for SHA-256 but still
DB-enforced rather than assumed) and IS the lookup key
`RefreshTokenStore.get_by_hash` queries by. `refresh_tokens.family_id` gets
a plain (non-unique) index — `revoke_family` queries every row sharing one
family at once. `refresh_tokens.user_id` gets a plain index (the FK column)
plus the FK constraint itself, `ondelete` left at its default (RESTRICT) —
deleting a `User` row while it still has `RefreshToken` rows is refused by
the DB rather than silently cascading away a security-relevant audit trail
of that user's past sessions; this app never deletes `User` rows today
(`SoftDeleteMixin` is composed instead), so this default is not yet
exercised, but RESTRICT is still the safer default over CASCADE for this
particular child table.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("jti", sa.String(length=32), nullable=False),
        sa.Column("family_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
