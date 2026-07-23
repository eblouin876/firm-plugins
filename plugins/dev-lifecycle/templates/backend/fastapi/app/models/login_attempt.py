"""Stage 5c (#45): the `LoginAttempt` model the vendored auth component's
`LockoutStore` protocol is implemented against (see
`app/core/security/auth/stores.py`) — one row per account currently being
tracked for failed-login lockout bookkeeping, persisted exactly as
`_core.AttemptRecord` describes (`_core.LockoutPolicy`'s own docstring is
THE reference for what this table's `failure_count`/`first_failure_at`/
`last_failure_at`/`locked_until` columns mean at each state — ALL of the
counting/threshold/rolling-window logic lives in `LockoutPolicy`, not here;
this model is dumb persistence for whatever `AttemptRecord` it hands us).
Not a vendored file itself — built on top of the vendored
`app/core/db/mixins.py`.

`account_key` stores the id `_core.AuthService.login` passes AS TEXT (a
plain `String`, not a `Uuid` `ForeignKey`) — `_core.LockoutStore`'s own
docstring notes a framework adapter is free to key it some other way than a
bare user id (e.g. `f"{user_id}:{client_ip}"`); a plain `String` column,
UNIQUE (one row per account_key, matching `LockoutPolicy`'s "the one row per
account" contract — see `SqlAlchemyLockoutStore.upsert`) keeps this table
correct for either keying scheme without assuming `account_key` is always a
`User.id`.

Deliberately composes `UUIDPrimaryKey` only — no `TimestampMixin`/
`SoftDeleteMixin`: `first_failure_at`/`last_failure_at`/`locked_until` are
each already explicit, application-supplied columns (`LockoutPolicy`'s own
injected `now()`), and a lockout row is deleted outright by `clear()`
(`_core.LockoutPolicy.clear` -> `LockoutStore.clear`), never soft-deleted —
there is no "tombstone" state worth keeping around for spent lockout
bookkeeping the way there is for a used refresh/single-use token."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKey


class LoginAttempt(Base, UUIDPrimaryKey):
    __tablename__ = "login_attempts"

    account_key: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
