"""Stage 13d: blog/CMS -- blog_posts, blog_comments

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Adds `blog_posts` (`app/models/blog_post.py`) and `blog_comments`
(`app/models/comment.py`) column-for-column, written by hand rather than
via `alembic revision --autogenerate` (no live DB was used to generate
this file, matching 0001-0004's own convention).

`blog_posts.author_id` and `blog_comments.{post_id,author_id}` FKs are
left at their DB-level default `ondelete` (RESTRICT) -- see each model's
own docstring for the "don't silently cascade away authored content"
rationale, the same posture `0002_create_auth_tables.py` documents for
`refresh_tokens.user_id`. Indexes: `blog_posts.slug` (`uq_blog_posts_
slug_active`, a PARTIAL UNIQUE index, `WHERE deleted_at IS NULL` -- the
DB-level backstop behind `app/schemas/blog.py`'s request-boundary slug
pattern/uniqueness check, scoped to match `app/api/routers/blog.py`'s
`_slug_taken`'s own `not_deleted()`-scoped friendly-error-path check --
see `app/models/blog_post.py`'s own docstring on why a PLAIN full-table
unique index would disagree with that check and 500 on a soft-deleted
slug's reuse), `blog_posts.{author_id,status}`, `blog_comments.
{post_id,author_id,status}` -- the plan's own "indexes on slug + post_id
+ status" requirement, plus the FK columns themselves (queried directly
by the admin list/filter endpoints, `app/api/routers/blog.py`)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_json", sa.JSON(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_blog_posts_author_id_users"),
    )
    # Partial unique index (WHERE deleted_at IS NULL), not a plain
    # column-level UNIQUE -- matches app/models/blog_post.py's
    # `__table_args__` exactly; both `sqlite_where=` and
    # `postgresql_where=` are set (unlike 0001_create_items_table.py's
    # non-unique `ix_items_deleted_at_null`, this one is UNIQUE, so it
    # must actually be partial on sqlite too -- see that model's own
    # docstring).
    op.create_index(
        "uq_blog_posts_slug_active",
        "blog_posts",
        ["slug"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_blog_posts_author_id", "blog_posts", ["author_id"], unique=False)
    op.create_index("ix_blog_posts_status", "blog_posts", ["status"], unique=False)

    op.create_table(
        "blog_comments",
        sa.Column("id", sa.Uuid(as_uuid=True, native_uuid=True), primary_key=True),
        sa.Column("post_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=False),
        sa.Column("author_id", sa.Uuid(as_uuid=True, native_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="visible"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["blog_posts.id"], name="fk_blog_comments_post_id_blog_posts"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_blog_comments_author_id_users"),
    )
    op.create_index("ix_blog_comments_post_id", "blog_comments", ["post_id"], unique=False)
    op.create_index("ix_blog_comments_author_id", "blog_comments", ["author_id"], unique=False)
    op.create_index("ix_blog_comments_status", "blog_comments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_blog_comments_status", table_name="blog_comments")
    op.drop_index("ix_blog_comments_author_id", table_name="blog_comments")
    op.drop_index("ix_blog_comments_post_id", table_name="blog_comments")
    op.drop_table("blog_comments")

    op.drop_index("ix_blog_posts_status", table_name="blog_posts")
    op.drop_index("ix_blog_posts_author_id", table_name="blog_posts")
    op.drop_index("uq_blog_posts_slug_active", table_name="blog_posts")
    op.drop_table("blog_posts")
