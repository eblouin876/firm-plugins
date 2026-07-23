"""Stage 13b: admin user management -- users.status

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

Adds `users.status` (`app/models/user.py`) column-for-column: a plain
`String(16)`, NOT a DB-level enum -- matching how `users.roles`/
`single_use_tokens.purpose` are stored (see `User`'s own module docstring
for the full "hermetic sqlite testability" rationale) -- with a real
`server_default='active'` so this migration backfills every pre-existing
row to a real, non-NULL `'active'` rather than leaving it undefined. Same
`server_default`-vs-`default` two-layer precedent 0003 already established
for `users.email_verified` (see that migration's own docstring). Written by
hand rather than via `alembic revision --autogenerate` (no live DB was used
to generate this file), matching 0001/0002/0003's own convention."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_column("users", "status")
