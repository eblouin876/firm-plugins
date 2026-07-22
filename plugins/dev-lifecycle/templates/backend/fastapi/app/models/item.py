"""The contract exemplar model: a minimal `Item` composing all three
vendored db-mixins (UUIDPrimaryKey + TimestampMixin + SoftDeleteMixin) so
the CRUD router, the repository, pagination, and the Alembic migration all
have one real table to exercise end to end. Not a vendored file itself —
this is Step 2's own app code, built on top of the vendored
app/core/db/mixins.py."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Item(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
