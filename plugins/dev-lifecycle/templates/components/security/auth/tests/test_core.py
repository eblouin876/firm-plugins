"""Exhaustive tests for auth's _core.py: Argon2id password hashing, PyJWT
access/refresh tokens, and -- the security-critical core of this
component -- the refresh-token rotation-with-reuse-detection state
machine. Async tests use explicit `@pytest.mark.asyncio` markers --
pytest-asyncio's default "strict" mode picks them up with no extra
`--asyncio-mode` flag or ini configuration needed (matches this catalog's
db-session component)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import TEST_SIGNING_KEY

# ---------------------------------------------------------------------------
# PasswordService
# ---------------------------------------------------------------------------


def test_hash_does_not_return_plaintext(password_service):
    hashed = password_service.hash("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert hashed.startswith("$argon2id$")


def test_verify_true_for_correct_password(password_service):
    hashed = password_service.hash("correct-horse-battery-staple")
    assert password_service.verify(hashed, "correct-horse-battery-staple") is True


def test_verify_false_for_wrong_password(password_service):
    hashed = password_service.hash("correct-horse-battery-staple")
    assert password_service.verify(hashed, "wrong-password") is False


def test_verify_false_for_malformed_stored_hash(password_service):
    # Not a valid Argon2 hash string at all -- InvalidHashError internally,
    # collapsed to False like a mismatch (see PasswordService.verify's
    # docstring on not distinguishing the two).
    assert password_service.verify("not-an-argon2-hash", "anything") is False


def test_needs_rehash_false_on_a_fresh_hash(password_service):
    hashed = password_service.hash("correct-horse-battery-staple")
    assert password_service.needs_rehash(hashed) is False


def test_needs_rehash_true_when_parameters_changed(core_mod):
    from argon2 import PasswordHasher

    weak_service = core_mod.PasswordService(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    weak_hash = weak_service.hash("correct-horse-battery-staple")

    strong_service = core_mod.PasswordService(PasswordHasher(time_cost=4, memory_cost=1024, parallelism=2))
    assert strong_service.needs_rehash(weak_hash) is True


def test_dummy_verify_runs_without_raising(password_service):
    password_service.dummy_verify()  # must not raise


def test_dummy_verify_is_independent_of_input(password_service):
    # dummy_verify() takes no arguments -- calling it repeatedly must
    # never raise or otherwise vary in a way that leaks anything.
    for _ in range(3):
        password_service.dummy_verify()


# ---------------------------------------------------------------------------
# TokenService: minting and round-tripping
# ---------------------------------------------------------------------------


def test_access_token_round_trips(token_service):
    token = token_service.mint_access("user-1", ["admin", "user"])
    claims = token_service.decode_access(token)
    assert claims.sub == "user-1"
    assert claims.roles == ["admin", "user"]
    assert claims.jti


def test_refresh_token_round_trips(token_service):
    token, minted_claims = token_service.mint_refresh("user-1", "family-1")
    decoded_claims = token_service.decode_refresh(token)
    assert decoded_claims.sub == "user-1"
    assert decoded_claims.family_id == "family-1"
    assert decoded_claims.jti == minted_claims.jti
    assert decoded_claims.expires_at == minted_claims.expires_at


def test_mint_refresh_returns_matching_raw_token_and_claims(token_service):
    token, claims = token_service.mint_refresh("user-1", "family-1")
    # The claims returned directly must match what decoding the raw token
    # separately produces -- the whole point of returning both together.
    redecoded = token_service.decode_refresh(token)
    assert claims.sub == redecoded.sub
    assert claims.jti == redecoded.jti
    assert claims.family_id == redecoded.family_id


def test_each_minted_token_has_a_unique_jti(token_service):
    token_a = token_service.mint_access("user-1", [])
    token_b = token_service.mint_access("user-1", [])
    claims_a = token_service.decode_access(token_a)
    claims_b = token_service.decode_access(token_b)
    assert claims_a.jti != claims_b.jti


def test_tampered_signature_is_rejected(core_mod, token_service):
    token = token_service.mint_access("user-1", [])
    tampered = token[:-1] + ("A" if not token.endswith("A") else "B")
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_access(tampered)


def test_expired_access_token_is_rejected(core_mod, token_service, clock):
    token = token_service.mint_access("user-1", [])
    clock.advance(timedelta(minutes=6))  # past the 5-minute access_ttl
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_access(token)


def test_expired_refresh_token_is_rejected(core_mod, token_service, clock):
    token, _claims = token_service.mint_refresh("user-1", "family-1")
    clock.advance(timedelta(days=8))  # past the 7-day refresh_ttl
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_refresh(token)


def test_token_valid_up_to_but_not_past_ttl(token_service, clock):
    token = token_service.mint_access("user-1", [])
    clock.advance(timedelta(minutes=4, seconds=59))  # just under the 5-minute ttl
    token_service.decode_access(token)  # must not raise


def test_wrong_secret_is_rejected(core_mod, token_service, clock):
    token = token_service.mint_access("user-1", [])
    other = core_mod.TokenService(
        "a-completely-different-signing-key-value",
        issuer="test-issuer",
        access_ttl=timedelta(minutes=5),
        refresh_ttl=timedelta(days=7),
        now=clock,
    )
    with pytest.raises(core_mod.InvalidToken):
        other.decode_access(token)


def test_issuer_mismatch_is_rejected(core_mod, clock):
    minting_service = core_mod.TokenService(
        TEST_SIGNING_KEY,
        issuer="issuer-a",
        access_ttl=timedelta(minutes=5),
        refresh_ttl=timedelta(days=7),
        now=clock,
    )
    verifying_service = core_mod.TokenService(
        TEST_SIGNING_KEY,
        issuer="issuer-b",
        access_ttl=timedelta(minutes=5),
        refresh_ttl=timedelta(days=7),
        now=clock,
    )
    token = minting_service.mint_access("user-1", [])
    with pytest.raises(core_mod.InvalidToken):
        verifying_service.decode_access(token)


def test_access_token_presented_as_refresh_is_rejected(core_mod, token_service):
    access_token = token_service.mint_access("user-1", [])
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_refresh(access_token)


def test_refresh_token_presented_as_access_is_rejected(core_mod, token_service):
    refresh_token, _claims = token_service.mint_refresh("user-1", "family-1")
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_access(refresh_token)


def test_malformed_token_string_is_rejected(core_mod, token_service):
    with pytest.raises(core_mod.InvalidToken):
        token_service.decode_access("this-is-not-a-jwt-at-all")


def test_token_service_rejects_empty_signing_key(core_mod, clock):
    with pytest.raises(ValueError):
        core_mod.TokenService(
            "",
            issuer="test-issuer",
            access_ttl=timedelta(minutes=5),
            refresh_ttl=timedelta(days=7),
            now=clock,
        )


def test_hash_token_is_sha256_hex(core_mod):
    digest = core_mod.hash_token("some-raw-token-value")
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex


def test_hash_token_is_deterministic(core_mod):
    assert core_mod.hash_token("same-value") == core_mod.hash_token("same-value")


def test_hash_token_differs_for_different_input(core_mod):
    assert core_mod.hash_token("value-a") != core_mod.hash_token("value-b")


# ---------------------------------------------------------------------------
# AuthService.register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_creates_a_user(auth_service):
    user = await auth_service.register("alice@example.com", "hunter2-plus-extra")
    assert user.email == "alice@example.com"
    assert user.password_hash != "hunter2-plus-extra"


@pytest.mark.asyncio
async def test_register_duplicate_email_raises(core_mod, auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.EmailAlreadyExists):
        await auth_service.register("alice@example.com", "different-password")


@pytest.mark.asyncio
async def test_register_normalizes_email_case_and_whitespace(auth_service):
    user = await auth_service.register("  Alice@Example.COM  ", "hunter2-plus-extra")
    assert user.email == "alice@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_detected_across_normalization(core_mod, auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.EmailAlreadyExists):
        await auth_service.register("  ALICE@EXAMPLE.COM", "different-password")


@pytest.mark.asyncio
async def test_register_stores_roles(auth_service):
    user = await auth_service.register("alice@example.com", "hunter2-plus-extra", roles=("admin",))
    assert user.roles == ("admin",)


# ---------------------------------------------------------------------------
# AuthService.login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_returns_usable_pair(auth_service, token_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    claims = token_service.decode_access(pair.access)
    assert claims.sub  # a real, decodable access token
    refresh_claims = token_service.decode_refresh(pair.refresh)
    assert refresh_claims.sub == claims.sub


@pytest.mark.asyncio
async def test_login_unknown_email_raises_invalid_credentials(core_mod, auth_service):
    with pytest.raises(core_mod.InvalidCredentials):
        await auth_service.login("nobody@example.com", "whatever-password")


@pytest.mark.asyncio
async def test_login_unknown_email_does_not_raise_or_leak_via_dummy_verify(auth_service, monkeypatch, core_mod):
    calls = []
    original = core_mod.PasswordService.dummy_verify

    def spy(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(core_mod.PasswordService, "dummy_verify", spy)
    with pytest.raises(core_mod.InvalidCredentials):
        await auth_service.login("nobody@example.com", "whatever-password")
    assert calls == [True]  # the timing-defense path was actually taken


@pytest.mark.asyncio
async def test_login_wrong_password_raises_invalid_credentials(core_mod, auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.InvalidCredentials):
        await auth_service.login("alice@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_login_wrong_password_and_unknown_email_raise_the_same_exception_type(core_mod, auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.InvalidCredentials) as wrong_pw_exc:
        await auth_service.login("alice@example.com", "wrong-password")
    with pytest.raises(core_mod.InvalidCredentials) as unknown_exc:
        await auth_service.login("nobody@example.com", "wrong-password")
    # Same exception type AND same message -- no distinguishing signal.
    assert type(wrong_pw_exc.value) is type(unknown_exc.value)
    assert str(wrong_pw_exc.value) == str(unknown_exc.value)


@pytest.mark.asyncio
async def test_login_persists_a_refresh_record(auth_service, refresh_store, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    record = await refresh_store.get_by_hash(core_mod.hash_token(pair.refresh))
    assert record is not None
    assert record.used_at is None
    assert record.revoked is False


# ---------------------------------------------------------------------------
# AuthService.refresh -- THE rotation-with-reuse-detection state machine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_happy_path_rotates(auth_service, refresh_store, token_service, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    new_pair = await auth_service.refresh(pair.refresh)

    # New pair differs from the old one entirely.
    assert new_pair.access != pair.access
    assert new_pair.refresh != pair.refresh

    # Old row now has used_at set.
    old_row = await refresh_store.get_by_hash(core_mod.hash_token(pair.refresh))
    assert old_row is not None
    assert old_row.used_at is not None
    assert old_row.revoked is False

    # New row present and NOT used.
    new_row = await refresh_store.get_by_hash(core_mod.hash_token(new_pair.refresh))
    assert new_row is not None
    assert new_row.used_at is None

    # Same family.
    new_claims = token_service.decode_refresh(new_pair.refresh)
    old_claims = token_service.decode_refresh(pair.refresh)
    assert new_claims.family_id == old_claims.family_id
    assert old_row.family_id == new_row.family_id


@pytest.mark.asyncio
async def test_refresh_reuse_is_detected_and_revokes_the_whole_family(auth_service, refresh_store, core_mod):
    """THE crown-jewel test: rotate once, then present the ORIGINAL
    (now-used) refresh token again -- must raise TokenReused AND kill
    every row in that family, including the freshly-minted valid child."""
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    original_pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    rotated_pair = await auth_service.refresh(original_pair.refresh)

    # Present the original (already-used) token again.
    with pytest.raises(core_mod.TokenReused):
        await auth_service.refresh(original_pair.refresh)

    # The whole family is now revoked -- verify directly on the store.
    original_row = await refresh_store.get_by_hash(core_mod.hash_token(original_pair.refresh))
    rotated_row = await refresh_store.get_by_hash(core_mod.hash_token(rotated_pair.refresh))
    assert original_row is not None and original_row.revoked is True
    assert rotated_row is not None and rotated_row.revoked is True

    # The just-minted, otherwise-still-valid child ALSO stops working now.
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(rotated_pair.refresh)


@pytest.mark.asyncio
async def test_refresh_from_an_already_revoked_family_is_invalid_token(auth_service, refresh_store, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    await auth_service.logout(pair.refresh)  # revokes the family

    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(pair.refresh)


@pytest.mark.asyncio
async def test_refresh_unknown_but_validly_signed_token_is_invalid_token(
    auth_service, refresh_store, token_service, core_mod
):
    # A validly-signed refresh JWT that was never persisted (e.g. minted
    # by a different, unrelated flow, or the store lost the row).
    forged_but_validly_signed, _claims = token_service.mint_refresh("some-user-id", "some-family-id")

    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(forged_but_validly_signed)

    # Critically: no row existed, so nothing should have been revoked --
    # the state machine must not trust the token's own claims to revoke
    # a family that was never on file.
    assert refresh_store.revoke_family_calls == []


@pytest.mark.asyncio
async def test_refresh_expired_row_is_invalid_token(auth_service, clock, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    clock.advance(timedelta(days=8))  # past the 7-day refresh_ttl

    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(pair.refresh)


@pytest.mark.asyncio
async def test_refresh_chain_can_rotate_multiple_times(auth_service, token_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    original_family = token_service.decode_refresh(pair.refresh).family_id

    for _ in range(5):
        pair = await auth_service.refresh(pair.refresh)
        assert token_service.decode_refresh(pair.refresh).family_id == original_family

    # The latest token in the chain is still valid.
    final_pair = await auth_service.refresh(pair.refresh)
    assert final_pair is not None


@pytest.mark.asyncio
async def test_refresh_with_garbage_token_raises_invalid_token(core_mod, auth_service):
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh("not-a-jwt-at-all")


@pytest.mark.asyncio
async def test_refresh_with_an_access_token_raises_invalid_token(core_mod, auth_service, token_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(pair.access)


# ---------------------------------------------------------------------------
# AuthService.logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_revokes_the_family(auth_service, refresh_store, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    await auth_service.logout(pair.refresh)

    row = await refresh_store.get_by_hash(core_mod.hash_token(pair.refresh))
    assert row is not None
    assert row.revoked is True


@pytest.mark.asyncio
async def test_logout_then_refresh_with_any_family_token_is_invalid(auth_service, core_mod):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    rotated_pair = await auth_service.refresh(pair.refresh)

    await auth_service.logout(rotated_pair.refresh)

    with pytest.raises(core_mod.InvalidToken):
        await auth_service.refresh(rotated_pair.refresh)


@pytest.mark.asyncio
async def test_logout_with_garbage_token_does_not_raise(auth_service):
    await auth_service.logout("totally-not-a-jwt")  # must not raise


@pytest.mark.asyncio
async def test_logout_with_unknown_but_validly_signed_token_does_not_raise(auth_service, token_service):
    forged_but_validly_signed, _claims = token_service.mint_refresh("some-user-id", "some-family-id")
    await auth_service.logout(forged_but_validly_signed)  # must not raise


@pytest.mark.asyncio
async def test_logout_is_idempotent(auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    await auth_service.logout(pair.refresh)
    await auth_service.logout(pair.refresh)  # second call must not raise either


@pytest.mark.asyncio
async def test_logout_with_an_access_token_does_not_raise(auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    await auth_service.logout(pair.access)  # wrong type -- decode fails -- swallowed, no raise


# ---------------------------------------------------------------------------
# AuthService.resolve_access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_access_returns_claims_with_roles(auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra", roles=("admin", "user"))
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")

    claims = await auth_service.resolve_access(pair.access)

    assert claims.roles == ["admin", "user"]
    assert claims.sub


@pytest.mark.asyncio
async def test_resolve_access_invalid_token_raises(core_mod, auth_service):
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.resolve_access("garbage-token")


@pytest.mark.asyncio
async def test_resolve_access_rejects_a_refresh_token(core_mod, auth_service):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.resolve_access(pair.refresh)


@pytest.mark.asyncio
async def test_resolve_access_rejects_an_expired_access_token(core_mod, auth_service, clock):
    await auth_service.register("alice@example.com", "hunter2-plus-extra")
    pair = await auth_service.login("alice@example.com", "hunter2-plus-extra")
    clock.advance(timedelta(minutes=6))
    with pytest.raises(core_mod.InvalidToken):
        await auth_service.resolve_access(pair.access)
