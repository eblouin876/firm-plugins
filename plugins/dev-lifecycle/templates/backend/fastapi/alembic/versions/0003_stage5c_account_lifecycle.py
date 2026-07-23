"""Stage 5c account lifecycle: verify + lockout tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

Matches app/models/user.py's added `email_verified`/`verified_at` columns,
app/models/single_use_token.py's `SingleUseToken` (UUIDPrimaryKey only), and
app/models/login_attempt.py's `LoginAttempt` (UUIDPrimaryKey only)
column-for-column, written by hand rather than via
`alembic revision --autogenerate` (no live DB was used to generate this
file, per the offline-emittable requirement, matching 0001/0002's own
convention) — see README.md's Alembic section for the verification
transcript this migration was proved against (both `--sql` offline emission
and a real online run against Postgres 16).

Stage 5c (#45): `users.email_verified` gets `server_default=false` (in
addition to the ORM-level `default=False` on `User.email_verified`) so this
migration itself backfills every pre-existing row to a real, non-NULL
`false` rather than leaving it `NULL` for any row inserted before this
migration ran — the ORM-level default only ever applies to INSERTs the app
itself issues going forward, never to rows already on disk (same
`server_default` vs. `default`/`onupdate` distinction
`app/core/db/mixins.py`'s `TimestampMixin` docstring documents for
`created_at`/`updated_at`). `users.verified_at` is nullable with no default
-- `None` until `AccountService.verify_email` sets it.

`single_use_tokens.token_hash` gets a UNIQUE index for the same reason
0002's `refresh_tokens.token_hash` does (a hash collision, astronomically
unlikely for SHA-256 but still DB-enforced rather than assumed) and IS the
lookup key `SingleUseTokenStore.get_by_hash` queries by. `user_id` gets a
plain (non-unique) index plus the FK constraint (`ondelete` left at its
default, RESTRICT, same rationale 0002 gives for `refresh_tokens.user_id` --
deleting a `User` row while it still has outstanding/consumed single-use
token rows is refused rather than silently cascading away that history;
this app never hard-deletes `User` rows today, `SoftDeleteMixin` is composed
instead).

`login_attempts.account_key` gets a UNIQUE index -- `SqlAlchemyLockoutStore.
upsert` maintains exactly one row per account_key (see that store's own
docstring), and the DB-level uniqueness is the enforcement of last resort
against a concurrent insert race for the same account_key, matching this
migration's own precedent (0002's `users.email`/`refresh_tokens.token_hash`
unique indexes) of never relying on the app-level read-then-write alone.
`login_attempts` has NO foreign key to `users` -- `_core.LockoutStore`'s own
docstring notes `account_key` is free-form (not guaranteed to be exactly a
`User.id`), so this table is deliberately decoupled from `users` at the DB
level, matching app/models/login_attempt.py's own module docstring.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "single_use_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_single_use_tokens_user_id_users"
        ),
    )
    op.create_index(
        "ix_single_use_tokens_token_hash", "single_use_tokens", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_single_use_tokens_user_id", "single_use_tokens", ["user_id"], unique=False
    )

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("account_key", sa.String(length=320), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("first_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_login_attempts_account_key", "login_attempts", ["account_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_account_key", table_name="login_attempts")
    op.drop_table("login_attempts")

    op.drop_index("ix_single_use_tokens_user_id", table_name="single_use_tokens")
    op.drop_index("ix_single_use_tokens_token_hash", table_name="single_use_tokens")
    op.drop_table("single_use_tokens")

    op.drop_column("users", "verified_at")
    op.drop_column("users", "email_verified")
