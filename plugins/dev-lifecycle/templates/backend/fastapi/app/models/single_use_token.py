"""Stage 5c (#45): the `SingleUseToken` model the vendored auth component's
`SingleUseTokenStore` protocol is implemented against (see
`app/core/security/auth/stores.py`) — one row per issued email-verification
or password-reset token, persisted exactly as `_core.SingleUseTokenRecord`
describes: `token_hash` (never the raw token — see `_core.hash_token`'s own
docstring) is the lookup key, `used_at` implements the single-use/reuse-
rejection state (`_core.SingleUseTokenService.consume`'s docstring is THE
reference for what this table's rows mean at each state). Not a vendored
file itself — built on top of the vendored `app/core/db/mixins.py`, same
composition pattern as `app/models/refresh_token.py`.

Deliberately composes `UUIDPrimaryKey` only — NOT `TimestampMixin`/
`SoftDeleteMixin`: `created_at`/`expires_at`/`used_at` are each already
explicit, application-supplied columns (set from a `SingleUseTokenRecord`
built by `SingleUseTokenService.issue`/`consume` against its OWN injected
`now()` — exactly how `RefreshToken.issued_at`/`expires_at`/`used_at` above
are handled), so `TimestampMixin`'s server-default row-bookkeeping
`created_at`/`updated_at` would be redundant with (and could silently drift
from) this table's own domain `created_at`. A single-use token is never
soft-deleted either — its lifecycle is fully captured by `used_at`, matching
`RefreshToken`'s own "retain, don't delete" posture (see
`_core.SingleUseTokenRecord`'s own docstring on why a consumed row stays on
file rather than being removed)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKey


class SingleUseToken(Base, UUIDPrimaryKey):
    __tablename__ = "single_use_tokens"

    # UNIQUE — the lookup key `SingleUseTokenStore.get_by_hash` queries by
    # (SHA-256 hex digest of the raw token, per `_core.hash_token`).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # INDEXED (not unique) — a user can have more than one outstanding
    # single-use token (e.g. a verify token and a reset token at once).
    user_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    # "verify" or "reset" today — `_core.py` does not enumerate the allowed
    # values as a closed set (see `SingleUseTokenRecord`'s own docstring), so
    # this stays a plain String rather than a DB-level enum/CHECK constraint.
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
