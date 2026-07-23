"""HTTP-level auth parity suite (Stage 5b, #44) — the DRF counterpart to
`backend/fastapi`'s `tests/test_auth.py`, porting every one of that
module's scenarios over `rest_framework.test.APIClient` against the real
`core/views.py` `/auth/*` views and `core/exceptions.py`'s `AuthError` ->
`ErrorEnvelope` mapping (Stage 5b B2). See each test's own docstring for
what it proves; most carry over their FastAPI counterpart's reasoning
near-verbatim, translated to this block's Django-specific mechanics.

**`@pytest.mark.django_db(transaction=True)` is REQUIRED on every test
here** — same two reasons `tests/test_auth_stores.py`'s own module
docstring documents in full: (1) `DjangoRefreshTokenStore`'s durability
argument (autocommit, no explicit `commit()`) is only genuinely exercised
under real autocommit semantics, not pytest-django's default per-test
`atomic()` wrapper — and reuse detection specifically depends on a
concurrent-looking second presentation of a rotated token seeing the
first rotation's `used_at` write as already durable; (2) Django's async
ORM (`.acreate()`/`.afirst()`/`.aupdate()`, used throughout `core/
security/auth/stores.py`) is a known source of `SynchronousOnlyOperation`/
connection flakiness under a rolled-back `atomic()` block.

`JWT_SIGNING_KEY` needs no per-test override here (unlike backend/
fastapi's `auth_client` fixture, which must bypass its process-wide,
`lru_cache`d `get_settings()`): `config/settings_test.py` already sets a
real placeholder signing key via `os.environ.setdefault` before `config.
settings` is even imported (see that module's own docstring), and
`core/security/auth/stores.py:get_token_service()` reads `django.conf.
settings.JWT_SIGNING_KEY` fresh on every call — no cache to bypass. The
one test that needs an UNCONFIGURED key (`test_auth_endpoint_without_a_
configured_signing_key_fails_closed` below) uses Django's own
`override_settings(JWT_SIGNING_KEY=None)` for exactly that one test,
restored automatically afterward."""

from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from core.models import User

pytestmark = pytest.mark.django_db(transaction=True)


def _register(client: APIClient, email: str = "alice@example.com", password: str = "correct horse battery staple") -> dict:
    response = client.post("/auth/register", {"email": email, "password": password}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def _login(client: APIClient, email: str = "alice@example.com", password: str = "correct horse battery staple") -> dict:
    response = client.post("/auth/login", {"email": email, "password": password}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


# ---------------------------------------------------------------------------
# register -> login -> me happy path
# ---------------------------------------------------------------------------


def test_register_then_login_then_me_happy_path(api_client: APIClient) -> None:
    registered = _register(api_client)
    assert registered["email"] == "alice@example.com"
    assert registered["id"]

    tokens = _login(api_client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_response = api_client.get("/auth/me", HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["id"] == registered["id"]
    assert me_body["email"] == "alice@example.com"


def test_register_normalizes_and_persists_email_case(api_client: APIClient) -> None:
    """Sanity check the wire-level effect of `_core.AuthService.
    _normalize_email` (lowercase + strip) — registering with mixed case/
    whitespace round-trips to the normalized form."""
    registered = _register(api_client, email="  Alice@Example.COM ", password="correct horse battery staple")
    assert registered["email"] == "alice@example.com"

    # Login with a DIFFERENT case/whitespace variant of the same email
    # still succeeds -- both normalize to the same account.
    tokens = _login(api_client, email="ALICE@example.com", password="correct horse battery staple")
    assert tokens["access_token"]


# ---------------------------------------------------------------------------
# duplicate register -> 409 envelope
# ---------------------------------------------------------------------------


def test_duplicate_register_returns_409_conflict_envelope(api_client: APIClient) -> None:
    _register(api_client)
    response = api_client.post(
        "/auth/register", {"email": "alice@example.com", "password": "a different password"}, format="json"
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"]


# ---------------------------------------------------------------------------
# bad login -> 401 envelope
# ---------------------------------------------------------------------------


def test_login_with_unknown_email_returns_401_unauthenticated_envelope(api_client: APIClient) -> None:
    response = api_client.post("/auth/login", {"email": "nobody@example.com", "password": "whatever"}, format="json")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"


def test_login_with_wrong_password_returns_401_unauthenticated_envelope(api_client: APIClient) -> None:
    _register(api_client)
    response = api_client.post(
        "/auth/login", {"email": "alice@example.com", "password": "wrong password"}, format="json"
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# refresh rotates
# ---------------------------------------------------------------------------


def test_refresh_rotates_and_returns_a_new_pair(api_client: APIClient) -> None:
    _register(api_client)
    tokens = _login(api_client)

    response = api_client.post("/auth/refresh", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["access_token"]
    assert rotated["refresh_token"]
    # A genuinely NEW pair, not an echo of the presented tokens.
    assert rotated["access_token"] != tokens["access_token"]
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # The rotated access token is itself immediately usable.
    me_response = api_client.get("/auth/me", HTTP_AUTHORIZATION=f"Bearer {rotated['access_token']}")
    assert me_response.status_code == 200


# ---------------------------------------------------------------------------
# refresh reuse -> 401 AND the whole family is dead (the crown jewel)
# ---------------------------------------------------------------------------


def test_refresh_token_reuse_is_detected_and_kills_the_whole_family(api_client: APIClient) -> None:
    """THE reuse-detection proof, at the HTTP level (see
    `_core.AuthService.refresh`'s own docstring for the state machine this
    exercises end to end through real routes/DB rows, not the vendored
    component's own unit tests): replaying an already-rotated refresh
    token returns 401, and — more than just that one token being rejected
    — the ROTATED token that replaced it (the family's current, otherwise
    still-valid tip) is ALSO rejected afterward, proving the entire
    family was revoked, not just the specific reused row."""
    _register(api_client)
    original = _login(api_client)

    # Rotate once: original.refresh_token -> rotated (still a live,
    # unused, valid token at this point).
    first_refresh = api_client.post("/auth/refresh", {"refresh_token": original["refresh_token"]}, format="json")
    assert first_refresh.status_code == 200
    rotated = first_refresh.json()

    # REPLAY the already-used original refresh token -- reuse detected.
    replay = api_client.post("/auth/refresh", {"refresh_token": original["refresh_token"]}, format="json")
    assert replay.status_code == 401
    replay_body = replay.json()
    assert replay_body["error"]["code"] == "unauthenticated"

    # The family is now dead -- even the CURRENTLY-VALID rotated token
    # (never itself reused) no longer works, proving whole-family
    # revocation, not merely "that one presented token was rejected".
    second_refresh = api_client.post("/auth/refresh", {"refresh_token": rotated["refresh_token"]}, format="json")
    assert second_refresh.status_code == 401
    assert second_refresh.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# soft-deleted (deactivated) user -> auth fails CLOSED, not open
# ---------------------------------------------------------------------------


def _soft_delete_user_by_email(email: str) -> None:
    """Soft-deletes the `User` row matching `email` directly through the
    ORM (`User.all_objects` -- the unscoped manager, since `User.objects`
    already excludes soft-deleted rows by default) — exercises `User.
    mark_deleted()`, without needing a real "deactivate user" API endpoint
    (this app doesn't have one yet). Plain sync ORM is fine here (unlike
    `core/security/auth/stores.py`'s async-only rule) — this helper runs
    directly in the test's own sync context, not inside an `AuthService`
    call bridged via `async_to_sync`."""
    user = User.all_objects.get(email=email)
    user.mark_deleted()
    user.save(update_fields=["deleted_at"])


def test_soft_deleted_user_cannot_login_or_refresh(api_client: APIClient) -> None:
    """A soft-deleted (deactivated) user must NOT be able to log in, and a
    refresh token issued BEFORE deactivation must NOT be usable afterward
    -- both `DjangoUserStore.get_by_email`/`get_by_id` apply `User.
    objects`'s default `not_deleted()` scoping (see that store's own
    docstring, "SECURITY (soft-delete auth-bypass fix..."). Does NOT
    assert `/auth/me` with the pre-deletion ACCESS token is rejected --
    that token remains valid until its own expiry, by design (stateless
    JWTs)."""
    _register(api_client)
    tokens = _login(api_client)

    _soft_delete_user_by_email("alice@example.com")

    login_response = api_client.post(
        "/auth/login", {"email": "alice@example.com", "password": "correct horse battery staple"}, format="json"
    )
    assert login_response.status_code == 401
    assert login_response.json()["error"]["code"] == "unauthenticated"

    refresh_response = api_client.post("/auth/refresh", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# reuse vs. an ordinary invalid refresh token must be WIRE-INDISTINGUISHABLE
# ---------------------------------------------------------------------------


def test_reuse_and_invalid_refresh_responses_are_wire_indistinguishable(api_client: APIClient) -> None:
    """Drives a genuine reuse (rotate once, then replay the used token) and
    an ordinary invalid-token refresh (a well-formed-looking but unknown
    token), and asserts both land on the exact SAME response body -- not
    merely the same status/code, but byte-identical, including `message`.
    Also asserts the reuse body contains none of "reuse"/"revoked"/
    "family" -- the substrings `_core.TokenReused`'s own message carries,
    which must never reach the client (see `core/exceptions.py`'s FIX-B
    section)."""
    _register(api_client)
    original = _login(api_client)

    first_refresh = api_client.post("/auth/refresh", {"refresh_token": original["refresh_token"]}, format="json")
    assert first_refresh.status_code == 200

    # REUSE: replay the already-used original refresh token.
    reuse_response = api_client.post("/auth/refresh", {"refresh_token": original["refresh_token"]}, format="json")
    assert reuse_response.status_code == 401
    reuse_body = reuse_response.json()

    # ORDINARY invalid token: a well-formed-looking but entirely unknown
    # token (never issued by this app, so `TokenService.decode_refresh`
    # rejects it as a bad signature -- a different `InvalidToken` failure
    # mode than reuse, but must render identically).
    invalid_response = api_client.post("/auth/refresh", {"refresh_token": "not-even-a-jwt"}, format="json")
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


def test_logout_then_refresh_returns_401(api_client: APIClient) -> None:
    _register(api_client)
    tokens = _login(api_client)

    logout_response = api_client.post("/auth/logout", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert logout_response.status_code == 204
    assert logout_response.content == b""

    refresh_response = api_client.post("/auth/refresh", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"]["code"] == "unauthenticated"


def test_logout_is_idempotent(api_client: APIClient) -> None:
    """A second logout call with an already-revoked token still returns
    204, never an error -- `AuthService.logout`'s own documented,
    deliberate best-effort/idempotent contract. A garbage (never-issued)
    token doesn't 500 either."""
    _register(api_client)
    tokens = _login(api_client)

    first = api_client.post("/auth/logout", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert first.status_code == 204

    second = api_client.post("/auth/logout", {"refresh_token": tokens["refresh_token"]}, format="json")
    assert second.status_code == 204

    garbage = api_client.post("/auth/logout", {"refresh_token": "not-even-a-jwt"}, format="json")
    assert garbage.status_code == 204


# ---------------------------------------------------------------------------
# /me without/with-bad token -> 401 envelope
# ---------------------------------------------------------------------------


def test_me_without_credentials_returns_401_envelope(api_client: APIClient) -> None:
    response = api_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_garbage_bearer_token_returns_401_envelope(api_client: APIClient) -> None:
    response = api_client.get("/auth/me", HTTP_AUTHORIZATION="Bearer not-even-a-jwt")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_with_a_refresh_token_instead_of_an_access_token_returns_401(api_client: APIClient) -> None:
    """A refresh token presented where an access token is expected is
    REJECTED at `TokenService`'s own `type` claim check -- the two token
    kinds are not interchangeable."""
    _register(api_client)
    tokens = _login(api_client)
    response = api_client.get("/auth/me", HTTP_AUTHORIZATION=f"Bearer {tokens['refresh_token']}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# Auth not configured -> fails closed (500), never signs with no key
# ---------------------------------------------------------------------------


@override_settings(JWT_SIGNING_KEY=None)
def test_auth_endpoint_without_a_configured_signing_key_fails_closed(api_client: APIClient) -> None:
    """No `JWT_SIGNING_KEY` configured -- `get_token_service()`'s
    fail-closed guard (`core/security/auth/stores.py`'s
    `AuthNotConfiguredError`) refuses to construct a `TokenService`,
    surfacing as the app's generic 500 `internal_error` envelope (`core/
    exceptions.py`'s catch-all -- `AuthNotConfiguredError` is a plain
    `RuntimeError`, not an `AuthError`, so it is NOT caught by this
    handler's `AuthError` branch) rather than ever signing a token with an
    empty/absent key."""
    response = api_client.post(
        "/auth/register", {"email": "a@example.com", "password": "whatever-password"}, format="json"
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


# ---------------------------------------------------------------------------
# Bearer scheme still declared in OpenAPI
# ---------------------------------------------------------------------------


def test_bearer_scheme_is_declared_in_openapi() -> None:
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"


# ---------------------------------------------------------------------------
# Malformed/duplicate register bodies still 422 through the real route
# ---------------------------------------------------------------------------


def test_register_with_missing_password_returns_422_validation_failed_envelope(api_client: APIClient) -> None:
    response = api_client.post("/auth/register", {"email": "a@example.com"}, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_register_id_is_a_real_uuid(api_client: APIClient) -> None:
    registered = _register(api_client)
    # Round-trips through uuid.UUID without raising -- a real UUID string,
    # not e.g. the raw Django pk repr.
    assert uuid.UUID(registered["id"])
