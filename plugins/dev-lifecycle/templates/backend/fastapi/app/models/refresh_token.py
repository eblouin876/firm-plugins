"""Stage 5a (#41): the `RefreshToken` model the vendored auth component's
`RefreshTokenStore` protocol is implemented against (see
`app/core/security/auth/stores.py`) — one row per minted refresh token,
persisted exactly as `_core.RefreshRecord` describes: `token_hash` (never
the raw token — see `_core.hash_token`'s own docstring) is the lookup key,
`used_at`/`revoked` implement the rotation-with-reuse-detection state
machine (`_core.AuthService.refresh`'s docstring is THE reference for what
this table's rows mean at each state). Not a vendored file itself — built
on top of the vendored `app/core/db/mixins.py`, same composition pattern as
`app/models/item.py`/`app/models/user.py`.

Deliberately composes `UUIDPrimaryKey` + `TimestampMixin` only, NOT
`SoftDeleteMixin` — a refresh-token row is never "soft deleted"; its
lifecycle is fully captured by `used_at`/`revoked` already (see
`_core.RefreshRecord`'s own docstring on why a used row is RETAINED, not
deleted, soft or otherwise), and `SoftDeleteMixin`'s `not_deleted()`/
`mark_deleted()` have no meaning here that isn't already covered."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKey


class RefreshToken(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "refresh_tokens"

    # UNIQUE — the lookup key `RefreshTokenStore.get_by_hash` queries by
    # (SHA-256 hex digest of the raw token, per `_core.hash_token`).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    jti: Mapped[str] = mapped_column(String(32), nullable=False)
    # INDEXED (not unique) — `RefreshTokenStore.revoke_family` queries every
    # row sharing one `family_id` at once (reuse detection, logout).
    family_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
