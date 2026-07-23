"""Stage 5a (#41) — real auth behavior against the hermetic client, over
HTTP, exercising `AuthService` through the real `app/api/routers/auth.py`
handlers and the `AuthError` -> `ErrorEnvelope` exception handler
(`app/main.py`'s `_auth_error_handler`). Replaces the Stage 3 Step 2 stub
tests (every route used to unconditionally 501).

Uses `make_client` (not the plain `client` fixture) for every test that
actually calls an auth endpoint: the plain `client` fixture builds its app
from the process-wide, `lru_cache`d `get_settings()`, which never has
`JWT_SIGNING_KEY` set in this test process's environment (see
`app/core/security/auth/stores.py`'s `AuthNotConfiguredError` — the
fail-closed guard this app deliberately keeps in place) — `make_client`
instead builds a bespoke `Settings(...)` with an explicit
`jwt_signing_key=`, exactly like `tests/test_security_composition.py`
already does for its own bespoke config, bypassing that cache entirely."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.core.db import configure_engine, get_sessionmaker
from app.core.db.session import _reset_engine_for_tests
from app.main import create_app

from .conftest import _test_lifespan

# Import side effect: registers every model on Base.metadata -- see
# tests/test_error_envelope.py's identical import for why a fixture that
# builds its own app/engine (rather than reusing the `client` fixture)
# needs this too.
import app.models  # noqa: F401,E402
from app.models.user import User  # noqa: E402

_TEST_SIGNING_KEY = "hermetic-test-signing-key-do-not-use-in-prod"


@pytest.fixture()
def auth_client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client(jwt_signing_key=_TEST_SIGNING_KEY)


@pytest.fixture()
def unconfigured_auth_client() -> Iterator[TestClient]:
    """Same shape as `tests/test_error_envelope.py`'s `crashing_client`
    fixture: a fresh app/engine, `raise_server_exceptions=False` so a
    genuine 500 comes back as a real HTTP response instead of re-raising
    into the test process. Deliberately does NOT set `jwt_signing_key` —
    built via the plain `get_settings()` path (no `settings=` override),
    which never has `JWT_SIGNING_KEY` in this test process's environment
    (see this module's own docstring) — used by the one test proving the
    fail-closed guard actually fires."""
    configure_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    app = create_app(lifespan_ctx=_test_lifespan)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    _reset_engine_for_tests()


def _register(client: TestClient, email: str = "alice@example.com", password: str = "correct horse battery staple") -> dict:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, email: str = "alice@example.com", password: str = "correct horse battery staple") -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# register -> login -> me happy path
# ---------------------------------------------------------------------------


def test_register_then_login_then_me_happy_path(auth_client: TestClient) -> None:
    registered = _register(auth_client)
    assert registered["email"] == "alice@example.com"
    assert registered["id"]

    tokens = _login(auth_client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["id"] == registered["id"]
    assert me_body["email"] == "alice@example.com"


def test_register_normalizes_and_persists_email_case(auth_client: TestClient) -> None:
    """Sanity check the wire-level effect of `_core.AuthService.
    _normalize_email` (lowercase + strip) — registering with mixed case/
    whitespace round-trips to the normalized form."""
    registered = _register(auth_client, email="  Alice@Example.COM ", password="correct horse battery staple")
    assert registered["email"] == "alice@example.com"

    # Login with a DIFFERENT case/whitespace variant of the same email
    # still succeeds -- both normalize to the same account.
    tokens = _login(auth_client, email="ALICE@example.com", password="correct horse battery staple")
    assert tokens["access_token"]


# ---------------------------------------------------------------------------
# duplicate register -> 409 envelope
# ---------------------------------------------------------------------------


def test_duplicate_register_returns_409_conflict_envelope(auth_client: TestClient) -> None:
    _register(auth_client)
    response = auth_client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "a different password"}
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"]


# ---------------------------------------------------------------------------
# bad login -> 401 envelope
# ---------------------------------------------------------------------------


def test_login_with_unknown_email_returns_401_unauthenticated_envelope(auth_client: TestClient) -> None:
    response = auth_client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"


def test_login_with_wrong_password_returns_401_unauthenticated_envelope(auth_client: TestClient) -> None:
    _register(auth_client)
    response = auth_client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong password"})
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# refresh rotates
# ---------------------------------------------------------------------------


def test_refresh_rotates_and_returns_a_new_pair(auth_client: TestClient) -> None:
    _register(auth_client)
    tokens = _login(auth_client)

    response = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["access_token"]
    assert rotated["refresh_token"]
    # A genuinely NEW pair, not an echo of the presented tokens.
    assert rotated["access_token"] != tokens["access_token"]
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # The rotated access token is itself immediately usable.
    me_response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me_response.status_code == 200


# ---------------------------------------------------------------------------
# refresh reuse -> 401 AND the whole family is dead (the crown jewel)
# ---------------------------------------------------------------------------


def test_refresh_token_reuse_is_detected_and_kills_the_whole_family(auth_client: TestClient) -> None:
    """THE reuse-detection proof, at the HTTP level (see
    `_core.AuthService.refresh`'s own docstring for the state machine this
    exercises end to end through real routes/DB rows, not the core's own
    unit tests): replaying an already-rotated refresh token returns 401,
    and — more than just that one token being rejected — the ROTATED
    token that replaced it (the family's current, otherwise still-valid
    tip) is ALSO rejected afterward, proving the entire family was
    revoked, not just the specific reused row."""
    _register(auth_client)
    original = _login(auth_client)

    # Rotate once: original.refresh_token -> rotated (still a live,
    # unused, valid token at this point).
    first_refresh = auth_client.post("/auth/refresh", json={"refresh_token": original["refresh_token"]})
    assert first_refresh.status_code == 200
    rotated = first_refresh.json()

    # REPLAY the already-used original refresh token -- reuse detected.
    replay = auth_client.post("/auth/refresh", json={"refresh_token": original["refresh_token"]})
    assert replay.status_code == 401
    replay_body = replay.json()
    assert replay_body["error"]["code"] == "unauthenticated"

    # The family is now dead -- even the CURRENTLY-VALID rotated token
    # (never itself reused) no longer works, proving whole-family
    # revocation, not merely "that one presented token was rejected".
    second_refresh = auth_client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert second_refresh.status_code == 401
    assert second_refresh.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# soft-deleted (deactivated) user -> auth fails CLOSED, not open
# ---------------------------------------------------------------------------


async def _soft_delete_user_by_email(email: str) -> None:
    """Soft-deletes the `User` row matching `email` directly through this
    app's own DB session/engine (`app.core.db.get_sessionmaker`, already
    configured by whichever `make_client(...)` call the calling test's
    fixture made) -- exercises `SoftDeleteMixin.mark_deleted()`, the exact
    mutation `AsyncRepository.delete()` itself calls, without needing a
    real "deactivate user" API endpoint (this app doesn't have one yet;
    that's a separate, later feature -- this test only needs the ROW in
    the deactivated state `stores.py`'s auth lookups must now honor)."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.mark_deleted()
        await session.commit()


def test_soft_deleted_user_cannot_login_or_refresh(auth_client: TestClient) -> None:
    """FIX (whole-PR review, Stage 5a, security MEDIUM): a soft-deleted
    (deactivated) user must NOT be able to log in, and a refresh token
    issued BEFORE deactivation must NOT be usable afterward -- both
    `SqlAlchemyUserStore.get_by_email`/`get_by_id` now apply
    `User.not_deleted()`, matching `AsyncRepository`'s own default. Does
    NOT assert `/auth/me` with the pre-deletion ACCESS token is rejected
    -- that token remains valid until its own expiry, by design (stateless
    JWTs -- see `stores.py`'s comment on this exact point)."""
    _register(auth_client)
    tokens = _login(auth_client)

    asyncio.run(_soft_delete_user_by_email("alice@example.com"))

    login_response = auth_client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "correct horse battery staple"}
    )
    assert login_response.status_code == 401
    assert login_response.json()["error"]["code"] == "unauthenticated"

    refresh_response = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# FIX (whole-PR review, Stage 5a, security LOW): reuse vs. an ordinary
# invalid refresh token must be WIRE-INDISTINGUISHABLE -- `_auth_error_
# handler` no longer echoes `str(exc)` for the 401 bucket.
# ---------------------------------------------------------------------------


def test_reuse_and_invalid_refresh_responses_are_wire_indistinguishable(auth_client: TestClient) -> None:
    """Drives a genuine reuse (rotate once, then replay the used token) and
    an ordinary invalid-token refresh (a well-formed-looking but unknown
    token), and asserts both land on the exact SAME response body -- not
    merely the same status/code, but byte-identical, including `message`.
    Also asserts the reuse body contains none of "reuse"/"revoked"/
    "family" -- the substrings `_core.TokenReused`'s own message carries,
    which must never reach the client (see `_core.py`'s `TokenReused`
    docstring and `_auth_error_handler`'s updated docstring in
    `app/main.py`)."""
    _register(auth_client)
    original = _login(auth_client)

    first_refresh = auth_client.post("/auth/refresh", json={"refresh_token": original["refresh_token"]})
    assert first_refresh.status_code == 200

    # REUSE: replay the already-used original refresh token.
    reuse_response = auth_client.post("/auth/refresh", json={"refresh_token": original["refresh_token"]})
    assert reuse_response.status_code == 401
    reuse_body = reuse_response.json()

    # ORDINARY invalid token: a well-formed-looking but entirely unknown
    # token (never issued by this app, so `TokenService.decode_refresh`
    # rejects it as a bad signature -- a different `InvalidToken` failure
    # mode than reuse, but must render identically).
    invalid_response = auth_client.post("/auth/refresh", json={"refresh_token": "not-even-a-jwt"})
    assert invalid_response.status_code == 401
    invalid_body = invalid_response.json()

    assert reuse_body == invalid_body

    reuse_message = reuse_body["error"]["message"].lower()
    assert "reuse" not in reuse_message
    assert "revoked" not in reuse_message
    assert "family" not in reuse_message


# ---------------------------------------------------------------------------
# logout -> 204, then refresh -> 401
# ---------------------------------------------------------------------------


def test_logout_then_refresh_returns_401(auth_client: TestClient) -> None:
    _register(auth_client)
    tokens = _login(auth_client)

    logout_response = auth_client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout_response.status_code == 204
    assert logout_response.content == b""

    refresh_response = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"]["code"] == "unauthenticated"


def test_logout_is_idempotent(auth_client: TestClient) -> None:
    """A second logout call with an already-revoked token still returns
    204, never an error -- `AuthService.logout`'s own documented,
    deliberate best-effort/idempotent contract."""
    _register(auth_client)
    tokens = _login(auth_client)

    first = auth_client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 204

    second = auth_client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert second.status_code == 204

    garbage = auth_client.post("/auth/logout", json={"refresh_token": "not-even-a-jwt"})
    assert garbage.status_code == 204


# ---------------------------------------------------------------------------
# /me without/with-bad token -> 401 envelope
# ---------------------------------------------------------------------------


def test_me_without_credentials_returns_401_envelope(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_garbage_bearer_token_returns_401_envelope(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me", headers={"Authorization": "Bearer not-even-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_a_refresh_token_instead_of_an_access_token_returns_401(auth_client: TestClient) -> None:
    """A refresh token presented where an access token is expected is
    REJECTED at `TokenService`'s own `type` claim check (`_core.py`'s
    `TokenService` docstring) -- the two token kinds are not
    interchangeable."""
    _register(auth_client)
    tokens = _login(auth_client)
    response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# Auth not configured -> fails closed (500), never signs with no key
# ---------------------------------------------------------------------------


def test_auth_endpoint_without_a_configured_signing_key_fails_closed(
    unconfigured_auth_client: TestClient,
) -> None:
    """No `JWT_SIGNING_KEY` configured -- `get_token_service()`'s
    fail-closed guard (`app/core/security/auth/stores.py`) refuses to
    construct a `TokenService`, surfacing as the app's generic 500
    `internal_error` envelope (the catch-all `Exception` handler — see
    app/main.py) rather than ever signing a token with an empty/absent
    key."""
    response = unconfigured_auth_client.post(
        "/auth/register", json={"email": "a@example.com", "password": "whatever-password"}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


# ---------------------------------------------------------------------------
# Bearer scheme still declared in OpenAPI
# ---------------------------------------------------------------------------


def test_bearer_scheme_is_declared_in_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"


# ---------------------------------------------------------------------------
# extra="forbid" still enforced on the new RegisterRequest schema
# ---------------------------------------------------------------------------


def test_register_rejects_unknown_fields(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "a-password", "is_admin": True},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
