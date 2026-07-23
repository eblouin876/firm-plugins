"""Unit tests for `core.exceptions.exception_handler`'s `AuthError` branch
(Stage 5b, #44) — calls the handler function DIRECTLY with a constructed
exception instance, not through a real HTTP request/view, since (unlike
`tests/test_conformance_errors.py`'s HTTP-level proofs) no real route needs
to exist yet to exercise every concrete `AuthError` subclass this handler
maps: `InsufficientRole` in particular has no dedicated route of its own
(role-gating isn't wired to any view in this block), so testing the
handler function in isolation is the only way to cover it here at all.

See `core/exceptions.py`'s own module docstring, "core.security.auth.
AuthError (Stage 5b, #44)", for the full mapping/FIX-B rationale this
module proves."""

from __future__ import annotations

import pytest

from core.exceptions import exception_handler
from core.security.auth import (
    EmailAlreadyExists,
    InsufficientRole,
    InvalidCredentials,
    InvalidToken,
    TokenReused,
)

# `AuthNotConfiguredError` is NOT part of `core.security.auth`'s public
# re-export (it lives in `core.security.auth.stores`, deliberately NOT
# re-exported by `core/security/auth/__init__.py` -- see that file's own
# docstring on the vendored-vs-app-code split) -- imported directly here,
# matching how a real caller (`core/views.py`) would reach it too.
from core.security.auth.stores import AuthNotConfiguredError


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (InvalidCredentials("wrong password"), 401, "unauthenticated"),
        (InvalidToken("Refresh token has expired."), 401, "unauthenticated"),
        (
            TokenReused("Refresh token reuse detected -- the token family has been revoked."),
            401,
            "unauthenticated",
        ),
        (EmailAlreadyExists("alice@example.com already has an account."), 409, "conflict"),
        (InsufficientRole("This action requires a role the current principal does not have."), 403, "permission_denied"),
    ],
)
def test_each_auth_error_subclass_maps_to_its_documented_status_and_code(
    exc: Exception, expected_status: int, expected_code: str
) -> None:
    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == expected_status
    body = response.data
    assert body["error"]["code"] == expected_code


@pytest.mark.parametrize(
    "exc",
    [
        InvalidCredentials("wrong password"),
        InvalidToken("Refresh token has expired."),
        TokenReused("Refresh token reuse detected -- the token family has been revoked."),
    ],
)
def test_unauthenticated_bucket_always_emits_the_same_generic_message(exc: Exception) -> None:
    """FIX B: every 401 `unauthenticated` `AuthError` -- including
    `TokenReused`, whose own message says exactly what happened -- renders
    the SAME fixed client-facing message, never `str(exc)`."""
    response = exception_handler(exc, {})

    assert response is not None
    assert response.data["error"]["message"] == "Authentication failed."


def test_reuse_message_never_reaches_the_client_body() -> None:
    """The literal proof: a `TokenReused` whose own message carries
    "reuse"/"revoked"/"family" must not leak any of those substrings into
    the rendered envelope -- an attacker holding a stolen, already-rotated
    refresh token must not be able to distinguish reuse detection firing
    from an ordinary invalid-token failure."""
    exc = TokenReused("Refresh token reuse detected -- the token family has been revoked.")

    response = exception_handler(exc, {})

    assert response is not None
    rendered = str(response.data).lower()
    assert "reuse" not in rendered
    assert "revoked" not in rendered
    assert "family" not in rendered


def test_conflict_and_permission_denied_still_echo_str_exc() -> None:
    """409 (`EmailAlreadyExists`) and 403 (`InsufficientRole`) are NOT part
    of the wire-uniform-401 posture -- neither carries a secret the way a
    refresh-token failure's exact cause does, so both keep surfacing their
    own message text."""
    conflict = EmailAlreadyExists("alice@example.com already has an account.")
    conflict_response = exception_handler(conflict, {})
    assert conflict_response is not None
    assert conflict_response.data["error"]["message"] == "alice@example.com already has an account."

    denied = InsufficientRole("This action requires a role the current principal does not have.")
    denied_response = exception_handler(denied, {})
    assert denied_response is not None
    assert denied_response.data["error"]["message"] == (
        "This action requires a role the current principal does not have."
    )


def test_an_unmapped_auth_error_subclass_fails_closed_to_401() -> None:
    """A hypothetical future `AuthError` subclass with no `AUTH_ERROR_HTTP`
    entry must still render as 401 `unauthenticated`, never a 500 that
    would leak "this specific auth exception type wasn't wired up" as an
    implementation detail."""
    from core.security.auth import AuthError

    class _SomeFutureAuthError(AuthError):
        pass

    response = exception_handler(_SomeFutureAuthError("unmapped"), {})

    assert response is not None
    assert response.status_code == 401
    assert response.data["error"]["code"] == "unauthenticated"
    assert response.data["error"]["message"] == "Authentication failed."


def test_auth_not_configured_error_is_not_caught_by_the_auth_error_branch() -> None:
    """`AuthNotConfiguredError` is a plain `RuntimeError`, NOT part of the
    `AuthError` hierarchy -- it must fall through this handler's `AuthError`
    branch entirely and land on the generic catch-all, rendering
    `internal_error` at 500, never `unauthenticated`/401 (which would
    incorrectly suggest a CLIENT-caused auth failure rather than a server
    misconfiguration)."""
    response = exception_handler(AuthNotConfiguredError("JWT_SIGNING_KEY is not configured."), {})

    assert response is not None
    assert response.status_code == 500
    assert response.data["error"]["code"] == "internal_error"
    # Never leaks the misconfiguration detail to the client -- same
    # "NEVER leak str(exc)" promise the module docstring makes for every
    # genuinely unhandled exception.
    assert "JWT_SIGNING_KEY" not in str(response.data)
