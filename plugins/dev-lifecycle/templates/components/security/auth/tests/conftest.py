"""Loads this component's `_core.py` under a private module name without
ever putting this directory on `sys.path` -- see security-headers/
tests/conftest.py's docstring for the full rationale (this component
mirrors the same load-by-file-path pattern rate-limiting/db-session/etc.
use throughout this catalog).

Also provides the shared test fixtures every test module in this
directory needs: in-memory fakes implementing `UserStore` and
`RefreshTokenStore` (plain dicts, no real database), an injectable/
advanceable `now`, a `TokenService` built against a fixed test signing
key, and a fully wired `AuthService`."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent


def _load(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, COMPONENT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


core = _load("_core", "_core.py")


@pytest.fixture(scope="session")
def core_mod() -> ModuleType:
    return core


# ---------------------------------------------------------------------------
# Injectable clock
# ---------------------------------------------------------------------------


class Clock:
    """A mutable, injectable clock -- `now()` returns whatever `current`
    is currently set to, and `advance()` moves it forward. Passed as the
    `now` callable to `TokenService`/`AuthService`, so a test can advance
    time deterministically (past a TTL, across a rotation) with no real
    sleeping and no monkeypatching of a module-global clock."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class FakeUserStore:
    """In-memory `UserStore` -- a dict keyed by normalized email, plus a
    parallel dict keyed by id for `get_by_id`."""

    def __init__(self) -> None:
        self._by_email: dict[str, "core.UserRecord"] = {}
        self._by_id: dict[str, "core.UserRecord"] = {}
        self._next_id = 1

    async def get_by_email(self, email):
        return self._by_email.get(email)

    async def get_by_id(self, id):
        return self._by_id.get(id)

    async def create(self, email, password_hash, roles):
        record = core.UserRecord(
            id=str(self._next_id),
            email=email,
            password_hash=password_hash,
            roles=tuple(roles),
        )
        self._next_id += 1
        self._by_email[email] = record
        self._by_id[record.id] = record
        return record


class FakeRefreshTokenStore:
    """In-memory `RefreshTokenStore` -- a dict keyed by `token_hash`.
    Tracks `revoke_family` calls (`revoke_family_calls`) so tests can
    assert it was -- or deliberately was NOT -- invoked."""

    def __init__(self) -> None:
        self._by_hash: dict[str, "core.RefreshRecord"] = {}
        self.revoke_family_calls: list[str] = []

    async def add(self, record):
        self._by_hash[record.token_hash] = record

    async def get_by_hash(self, token_hash):
        return self._by_hash.get(token_hash)

    async def mark_used(self, token_hash, used_at):
        existing = self._by_hash[token_hash]
        self._by_hash[token_hash] = core.RefreshRecord(
            token_hash=existing.token_hash,
            jti=existing.jti,
            family_id=existing.family_id,
            user_id=existing.user_id,
            issued_at=existing.issued_at,
            expires_at=existing.expires_at,
            used_at=used_at,
            revoked=existing.revoked,
        )

    async def revoke_family(self, family_id):
        self.revoke_family_calls.append(family_id)
        for token_hash, record in list(self._by_hash.items()):
            if record.family_id == family_id:
                self._by_hash[token_hash] = core.RefreshRecord(
                    token_hash=record.token_hash,
                    jti=record.jti,
                    family_id=record.family_id,
                    user_id=record.user_id,
                    issued_at=record.issued_at,
                    expires_at=record.expires_at,
                    used_at=record.used_at,
                    revoked=True,
                )

    def all_records(self):
        return list(self._by_hash.values())


@pytest.fixture
def user_store() -> FakeUserStore:
    return FakeUserStore()


@pytest.fixture
def refresh_store() -> FakeRefreshTokenStore:
    return FakeRefreshTokenStore()


TEST_SIGNING_KEY = "test-signing-key-not-for-real-use-at-least-32-bytes-long"


@pytest.fixture
def token_service(clock: Clock):
    return core.TokenService(
        TEST_SIGNING_KEY,
        issuer="test-issuer",
        access_ttl=timedelta(minutes=5),
        refresh_ttl=timedelta(days=7),
        now=clock,
    )


@pytest.fixture
def password_service():
    return core.PasswordService()


@pytest.fixture
def auth_service(user_store, refresh_store, password_service, token_service, clock):
    return core.AuthService(user_store, refresh_store, password_service, token_service, clock)
