"""Framework-neutral auth core: Argon2id password hashing (`PasswordService`),
PyJWT-based HS256 access/refresh tokens (`TokenService`), and the
`AuthService` orchestrator implementing register/login/refresh/logout --
including the refresh-token ROTATION-WITH-REUSE-DETECTION state machine,
the security-critical part of this module. Canon:
references/security/secure-baseline.md ("Hash passwords with a strong
adaptive algorithm... Tokens (JWT/session) validated fully -- signature,
expiry, audience/issuer -- with sensible expiry and secure rotation/
logout. Prefer short-lived access tokens with refresh over long-lived
static tokens").

Drop-in: copy this file into app/core/security/auth/_core.py (keep it
alongside fastapi.py/django.py from the same directory, once a later
stage adds them -- this component ships the framework-neutral core only;
wiring it into a FastAPI or Django backend block is separate work). Stdlib
+ PyJWT + argon2-cffi only -- **no FastAPI, Django, or SQLAlchemy import
anywhere in this file.** `UserStore` and `RefreshTokenStore` below are
`Protocol`s a framework adapter implements against its own ORM/session;
this module never touches a database, a request object, or a settings
object directly -- every secret/TTL/store it needs is passed in by the
caller.

**This file raises its OWN exception hierarchy** (`AuthError` and its
subclasses below) rather than importing
`templates/components/backend/error-envelope/errors.py`'s `AppError`/
`ErrorCode` -- that keeps this module importable with zero framework/
app-layer dependencies. Each exception's docstring names the `ErrorCode`
member (from that LOCKED, closed enum -- this module does NOT extend it)
a framework adapter's exception handler is expected to map it onto.

**The refresh-rotation state machine (`AuthService.refresh`) is the
security-critical core of this module** -- read its docstring and
`tests/test_core.py`'s reuse-detection tests before touching it. Summary:
every refresh token is single-use; presenting an already-used one means
the client's token was stolen and used by someone else first (or the
legitimate client raced itself) -- either way, the entire token FAMILY
(every token descended from one login) is revoked immediately, forcing a
fresh login. The persisted `RefreshRecord` (looked up by SHA-256 hash of
the raw token), never the JWT's own claims, is the sole source of truth
for whether a refresh token is still valid -- a validly-signed,
unexpired JWT whose row has been marked used/revoked/deleted is still
rejected, because trust lives in the store, not in what the client is
merely able to present.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# ---------------------------------------------------------------------------
# Core exception hierarchy
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Base of every exception this module raises deliberately (as
    opposed to letting an unexpected bug propagate unchanged -- see
    `PasswordService.verify`'s docstring on not catching unexpected
    errors). A framework adapter's exception handler catches this
    hierarchy and maps each concrete subclass onto an existing
    `ErrorCode` member from `templates/components/backend/error-envelope/
    errors.py` -- that enum is a LOCKED, closed set this module does NOT
    extend; every subclass below documents which member it maps to."""


class InvalidCredentials(AuthError):
    """Login failed -- either the email is not registered, or the
    password did not match. Maps to `ErrorCode.UNAUTHENTICATED` (401).

    Deliberately the SAME exception (and the SAME generic message) for
    both causes: `AuthService.login` raises this identically whether the
    email was never registered or the password was simply wrong, so a
    client (or an attacker probing for valid emails) cannot distinguish
    "no such account" from "wrong password" -- the classic user-
    enumeration-via-login-error class of bug. See `AuthService.login`'s
    own docstring for the timing-defense half of this (calling
    `PasswordService.dummy_verify()` on the not-found path)."""


class InvalidToken(AuthError):
    """A presented access or refresh token failed to validate. Covers
    every failure mode: bad signature, expired, wrong issuer, malformed/
    missing required claims, wrong `type` claim (an access token
    presented where a refresh token is expected, or vice versa), unknown
    to the refresh-token store (a validly-signed JWT with no matching
    persisted row), or belonging to a refresh-token family that has been
    revoked. Maps to `ErrorCode.UNAUTHENTICATED` (401).

    Deliberately indistinguishable, at this exception-TYPE level, from
    `TokenReused` below -- see that class's docstring for why a client
    must never be able to tell the two apart from the wire response."""


class TokenReused(AuthError):
    """A refresh token that was already rotated (its persisted record's
    `used_at` is already set) was presented again. This is the reuse-
    detection signal: single-use refresh tokens mean a second
    presentation of an already-used token means either (a) the token was
    stolen and an attacker used it after -- or before -- the legitimate
    client, or (b) the legitimate client raced itself (e.g. a retried
    request after a dropped response). Either way, this cannot be
    resolved safely, so raising this exception has ALREADY, as a side
    effect, revoked the token's entire FAMILY (every refresh token
    descended from the same login, via `RefreshTokenStore.revoke_family`)
    by the time the caller sees it -- see `AuthService.refresh`'s
    docstring for the full state machine.

    Maps to `ErrorCode.UNAUTHENTICATED` (401) -- the SAME code as
    `InvalidToken`, deliberately. A client must not be able to
    distinguish "reuse was detected and your whole session was killed"
    from "this token was simply invalid" from the wire response alone:
    revealing that distinction to whoever is holding the stolen-but-
    already-rotated token confirms reuse detection exists and just
    fired, which is exactly the information an attacker probing the
    endpoint would find useful. A server-side audit log is where reuse
    gets flagged for a human to investigate -- not the response the
    client (attacker or legitimate) receives."""


class EmailAlreadyExists(AuthError):
    """`AuthService.register` was called with an email that already has
    an account. Maps to `ErrorCode.CONFLICT` (409)."""


# ---------------------------------------------------------------------------
# Password hashing (Argon2id)
# ---------------------------------------------------------------------------


class PasswordService:
    """Wraps `argon2.PasswordHasher` -- Argon2id (argon2-cffi's default
    `Type.ID`) is left at its default, which this class does not
    override; Argon2id is the OWASP-recommended default for new
    applications (resistant to both GPU-cracking and side-channel
    attacks, unlike the pure-Argon2i/Argon2d variants). A custom
    `argon2.PasswordHasher` instance can be passed in (e.g. a project
    tuning `memory_cost`/`time_cost` for its own hardware budget) --
    `None` (the default) uses argon2-cffi's own library defaults, which
    are already reasonable for a starter kit."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()
        # A precomputed, throwaway Argon2id hash of a fixed, never-used
        # password -- see dummy_verify() below. Computed once at
        # construction, not per call, so dummy_verify()'s cost is exactly
        # one Argon2id verify, matching the cost of a real verify() call.
        self._dummy_hash = self._hasher.hash("dummy-password-never-used-for-a-real-account")

    def hash(self, password: str) -> str:
        """Hashes `password` with Argon2id, returning an encoded hash
        string that embeds the algorithm, its parameters, the salt, and
        the digest -- everything `verify()`/`needs_rehash()` need, so
        nothing else about the hashing parameters needs to be stored
        alongside it."""
        return self._hasher.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        """Returns `True` if `password` matches `stored_hash`, `False`
        otherwise. Both a wrong password (`VerifyMismatchError`) and a
        corrupt/foreign-format stored hash (`InvalidHashError`) collapse
        to the same `False` return -- deliberately: the caller must never
        be able to tell "wrong password" apart from "the stored hash
        itself is malformed" through this method's return value, which
        would leak information about the account's stored data rather
        than just whether the guess was right. Any OTHER exception
        (a bug, an unexpected argon2-cffi internal error) is NOT caught
        here and propagates -- silently converting an unexpected error
        into "verification failed" would hide real bugs (e.g. a
        misconfigured hasher) behind an indistinguishable-from-normal
        failed-login response."""
        try:
            self._hasher.verify(stored_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        return True

    def needs_rehash(self, stored_hash: str) -> bool:
        """Delegates to `PasswordHasher.check_needs_rehash` -- `True` when
        `stored_hash` was produced with different (typically weaker)
        parameters than this instance's current `time_cost`/
        `memory_cost`/`parallelism`/`type`. Lets a login flow
        transparently upgrade an old hash (recompute and store a fresh
        one right after a successful `verify()`) as this service's own
        parameters are tightened over time, without a bulk migration."""
        return self._hasher.check_needs_rehash(stored_hash)

    def dummy_verify(self) -> None:
        """User-enumeration timing defense: runs one Argon2id verify
        against a precomputed throwaway hash (see `__init__`), spending
        the same CPU time a real `verify()` call would, then discards the
        (always-`False`) result. `AuthService.login` calls this on the
        "email not found" path specifically so that path costs the same
        wall-clock time as the "email found, password checked" path --
        without it, an attacker could distinguish a registered email from
        an unregistered one purely by how fast the login endpoint
        responds (Argon2id's whole point is to be slow; skipping it
        entirely for unknown emails would make that slowness itself the
        leak). Never raises -- reuses `verify()`, which only ever returns
        `bool`."""
        self.verify(self._dummy_hash, "irrelevant-guess-always-mismatches")


# ---------------------------------------------------------------------------
# Tokens (PyJWT, HS256, shared secret)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessClaims:
    """The decoded, verified claims of an access token, as returned by
    `TokenService.decode_access` -- what `AuthService.resolve_access`
    hands back to a framework's `get_current_principal` dependency."""

    sub: str
    roles: list[str]
    jti: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RefreshClaims:
    """The decoded, verified claims of a refresh token. Also returned
    directly by `TokenService.mint_refresh` (alongside the raw JWT) so a
    caller can persist a `RefreshRecord` without a redundant decode of the
    token it just minted."""

    sub: str
    jti: str
    family_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class TokenPair:
    """An access/refresh token pair, as returned by every `AuthService`
    method that mints new tokens (`login`, `refresh`)."""

    access: str
    refresh: str


class TokenService:
    """Mints and verifies HS256 JWTs against one shared `signing_key`.

    `now` is a required, injected `Callable[[], datetime]` (no default --
    the framework layer supplies `lambda: datetime.now(timezone.utc)` or
    equivalent) so every test in `tests/` can advance time deterministically
    (expiry, rotation) without sleeping in a test or monkeypatching a
    module-global clock. `now()` MUST return a timezone-aware `datetime` in
    UTC -- a naive datetime would make the `exp`/`iat` timestamp math
    ambiguous about which timezone it's relative to.

    Access token claims: `sub` (principal id, as a string), `type`
    (literal `"access"`), `iat`, `exp`, `iss`, `jti` (a fresh `uuid4` hex
    per token), `roles` (list of role strings).

    Refresh token claims: `sub`, `type` (literal `"refresh"`), `iat`,
    `exp`, `iss`, `jti`, `fid` (the token's FAMILY id -- shared by every
    refresh token descended from one login, via rotation; see
    `AuthService.refresh`).

    Decoding verifies the signature (HS256 only -- `algorithms=["HS256"]`
    is passed explicitly on every decode call, never inferred from the
    token's own header, which would let a malicious token dictate its own
    verification algorithm), issuer, and the presence of every claim
    above via `options={"require": [...]}}`. **Expiry is checked
    manually against the injected `now()`, not PyJWT's own built-in
    wall-clock check** (`verify_exp`/`verify_iat` are explicitly turned
    OFF in the `options` passed to `jwt.decode`) -- PyJWT's own expiry
    validation always compares against the real system clock
    (`datetime.now(tz=timezone.utc)`) with no way to inject a substitute,
    which would make `tests/test_core.py`'s "advance the injected `now`
    past the TTL, assert `InvalidToken`" tests either flaky (racing the
    real clock) or entirely disconnected from the `now` this class was
    actually constructed with. Checking it manually, against the exact
    same `now` every other part of this class uses, is what makes expiry
    fully deterministic under test. Then additionally asserts the decoded
    `type` claim matches what the caller asked for
    (`decode_access` requires `type == "access"`, `decode_refresh`
    requires `type == "refresh"`). An access token presented where a
    refresh token is expected (or vice versa) is REJECTED at this `type`
    check, not silently accepted just because it happens to be a
    validly-signed JWT from the same issuer -- the two token kinds are
    security-distinct (a refresh token grants a NEW token pair; an access
    token does not) and must never be interchangeable.

    Every failure mode -- bad signature, expired, wrong issuer, malformed/
    missing claims, wrong `type` -- raises `InvalidToken`, never a raw
    `jwt.PyJWTError` subclass, so callers never need to import PyJWT's own
    exception hierarchy to handle a decode failure."""

    def __init__(
        self,
        signing_key: str,
        *,
        issuer: str,
        access_ttl: timedelta,
        refresh_ttl: timedelta,
        now: Callable[[], datetime],
    ) -> None:
        if not signing_key:
            raise ValueError("signing_key must not be empty -- an empty HS256 key is not a secret.")
        self._signing_key = signing_key
        self._issuer = issuer
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._now = now

    def mint_access(self, sub: str, roles: Sequence[str]) -> str:
        """Mints a fresh access token for principal `sub` with the given
        `roles`. `exp` is `now() + access_ttl`."""
        current = self._now()
        claims = {
            "sub": sub,
            "type": "access",
            "iat": _to_timestamp(current),
            "exp": _to_timestamp(current + self._access_ttl),
            "iss": self._issuer,
            "jti": uuid.uuid4().hex,
            "roles": list(roles),
        }
        return jwt.encode(claims, self._signing_key, algorithm="HS256")

    def mint_refresh(self, sub: str, family_id: str) -> tuple[str, RefreshClaims]:
        """Mints a fresh refresh token for principal `sub` in token family
        `family_id`. `exp` is `now() + refresh_ttl`. Returns BOTH the raw
        JWT (to hand to the client) AND its decoded `RefreshClaims` (so
        the caller -- `AuthService`'s rotation logic -- can build and
        persist a `RefreshRecord` without redundantly decoding the token
        it just minted)."""
        current = self._now()
        expires_at = current + self._refresh_ttl
        jti = uuid.uuid4().hex
        claims = {
            "sub": sub,
            "type": "refresh",
            "iat": _to_timestamp(current),
            "exp": _to_timestamp(expires_at),
            "iss": self._issuer,
            "jti": jti,
            "fid": family_id,
        }
        token = jwt.encode(claims, self._signing_key, algorithm="HS256")
        decoded = RefreshClaims(
            sub=sub,
            jti=jti,
            family_id=family_id,
            issued_at=current,
            expires_at=expires_at,
        )
        return token, decoded

    def decode_access(self, token: str) -> AccessClaims:
        """Verifies and decodes an access token. Raises `InvalidToken` on
        any failure, including a refresh token presented here."""
        payload = self._decode(token, expected_type="access")
        try:
            return AccessClaims(
                sub=str(payload["sub"]),
                roles=list(payload.get("roles", [])),
                jti=str(payload["jti"]),
                issued_at=_from_timestamp(payload["iat"]),
                expires_at=_from_timestamp(payload["exp"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidToken("The access token is malformed.") from exc

    def decode_refresh(self, token: str) -> RefreshClaims:
        """Verifies and decodes a refresh token. Raises `InvalidToken` on
        any failure, including an access token presented here."""
        payload = self._decode(token, expected_type="refresh")
        try:
            return RefreshClaims(
                sub=str(payload["sub"]),
                jti=str(payload["jti"]),
                family_id=str(payload["fid"]),
                issued_at=_from_timestamp(payload["iat"]),
                expires_at=_from_timestamp(payload["exp"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidToken("The refresh token is malformed.") from exc

    def _decode(self, token: str, *, expected_type: str) -> dict[str, object]:
        try:
            payload = jwt.decode(
                token,
                self._signing_key,
                algorithms=["HS256"],
                issuer=self._issuer,
                options={
                    "require": ["exp", "iat", "iss", "sub", "jti", "type"],
                    # Expiry is verified manually below, against this
                    # instance's injected `now()` -- see this class's
                    # docstring for why PyJWT's own built-in exp check
                    # (always against the real system clock) is turned off
                    # here rather than relied on.
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken("The token is invalid, expired, or malformed.") from exc
        if payload.get("type") != expected_type:
            raise InvalidToken(f"Expected a {expected_type!r} token, got {payload.get('type')!r}.")
        if self._now() >= _from_timestamp(payload["exp"]):
            raise InvalidToken("The token has expired.")
        return payload


def _to_timestamp(value: datetime) -> int:
    """Converts a timezone-aware `datetime` to a POSIX timestamp (whole
    seconds) for embedding as a JWT numeric-date claim (`iat`/`exp`)."""
    return int(value.timestamp())


def _from_timestamp(value: object) -> datetime:
    """Converts a JWT numeric-date claim back to a timezone-aware UTC
    `datetime`. Raises `TypeError`/`ValueError` on a non-numeric value --
    left uncaught here so `decode_access`/`decode_refresh`'s callers wrap
    it into `InvalidToken` (a malformed claim is a malformed token, not a
    crash)."""
    return datetime.fromtimestamp(float(value), tz=timezone.utc)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Refresh-token store: Protocol + record (server keeps SHA-256, never raw)
# ---------------------------------------------------------------------------


def hash_token(raw: str) -> str:
    """`hashlib.sha256(raw.encode()).hexdigest()` -- the ONLY form of a
    refresh token this module ever persists; the raw JWT itself is never
    written to storage.

    A fast cryptographic hash (SHA-256), not a slow password KDF (Argon2/
    bcrypt/scrypt), is the CORRECT choice here, deliberately different
    from `PasswordService` above: a password is a low-entropy secret a
    human chose, vulnerable to offline brute-force/dictionary attack
    against a stolen hash, which is exactly what a slow KDF defends
    against. A refresh token is a high-entropy value THIS module
    generated (a signed JWT, effectively random from an attacker's
    perspective) -- brute-forcing a SHA-256 preimage of a 256-bit-entropy
    input is computationally infeasible regardless of hash speed, so a
    slow KDF here would only add CPU cost on every single refresh-token
    lookup (every token refresh, every logout) for zero additional
    security. Hashing at all (rather than storing the raw token) still
    matters: it means a read-only compromise of the store's rows (a
    leaked DB backup, a compromised replica) does not hand out live,
    directly-usable refresh tokens."""
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class RefreshRecord:
    """One persisted refresh-token row. `token_hash` (from `hash_token`)
    is the lookup key -- never the raw token. `used_at` is `None` until
    the token is rotated (see `AuthService.refresh`), at which point it's
    set and the row is RETAINED, not deleted -- that retention is what
    lets a second presentation of the same (now-used) token be recognized
    as reuse rather than simply "not found". `revoked` is set on every row
    in a family at once by `RefreshTokenStore.revoke_family` (on reuse
    detection, or on logout)."""

    token_hash: str
    jti: str
    family_id: str
    user_id: str
    issued_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked: bool


class RefreshTokenStore(Protocol):
    """The storage seam `AuthService`'s refresh-rotation state machine
    runs against -- a framework adapter implements this against its own
    ORM/session (e.g. a SQLAlchemy or Django model table keyed by
    `token_hash`). All methods are `async` since a real implementation
    talks to a database.

    Implementations MUST make `add`/`mark_used`/`revoke_family` durable
    (committed) before returning -- `AuthService.refresh` relies on
    `mark_used` having taken effect before it returns the new token pair,
    so a concurrent second presentation of the just-rotated token sees the
    updated `used_at` and is correctly flagged as reuse rather than racing
    past this implementation's own write."""

    async def add(self, record: RefreshRecord) -> None: ...

    async def get_by_hash(self, token_hash: str) -> RefreshRecord | None: ...

    async def mark_used(self, token_hash: str, used_at: datetime) -> None: ...

    async def revoke_family(self, family_id: str) -> None: ...


# ---------------------------------------------------------------------------
# User store: Protocol + record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserRecord:
    """The minimal user shape `AuthService` needs -- deliberately NOT a
    full user profile (no name, no created_at, no arbitrary metadata);
    a framework adapter's own ORM model can carry more fields, this
    dataclass only needs to carry what `register`/`login`/`refresh` read
    or write."""

    id: str
    email: str
    password_hash: str
    roles: tuple[str, ...]


class UserStore(Protocol):
    """The storage seam `AuthService` runs registration/login against --
    a framework adapter implements this against its own user model. All
    methods `async`, matching `RefreshTokenStore`."""

    async def get_by_email(self, email: str) -> UserRecord | None: ...

    async def get_by_id(self, id: str) -> UserRecord | None: ...

    async def create(self, email: str, password_hash: str, roles: Sequence[str]) -> UserRecord: ...


# ---------------------------------------------------------------------------
# AuthService: the orchestrator + the reuse-detection state machine
# ---------------------------------------------------------------------------


class AuthService:
    """Orchestrates `UserStore`, `RefreshTokenStore`, `PasswordService`,
    and `TokenService` into `register`/`login`/`refresh`/`logout`/
    `resolve_access`. `now` is injected the same way `TokenService`'s is
    (required, no default) -- `AuthService` uses it for the refresh-
    rotation state machine's expiry comparison (`refresh`, step 5 below),
    independently of whatever `now` the `TokenService` instance it was
    constructed with also uses; a caller normally passes the SAME
    callable to both."""

    def __init__(
        self,
        users: UserStore,
        refresh_tokens: RefreshTokenStore,
        passwords: PasswordService,
        tokens: TokenService,
        now: Callable[[], datetime],
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._passwords = passwords
        self._tokens = tokens
        self._now = now

    @staticmethod
    def _normalize_email(email: str) -> str:
        """Lowercases and strips whitespace. Applied identically at
        registration and login lookup time so `"Alice@Example.com "` and
        `"alice@example.com"` are always treated as the same account --
        without this, a user could accidentally (or an attacker
        deliberately) register a case/whitespace variant of an existing
        email as a DISTINCT account, which most mail providers treat as
        delivering to the same inbox regardless of case."""
        return email.strip().lower()

    async def register(self, email: str, password: str, roles: Sequence[str] = ()) -> UserRecord:
        """Registers a new user. Raises `EmailAlreadyExists` if
        `_normalize_email(email)` is already on file. The password is
        hashed (`PasswordService.hash`) before it ever reaches
        `UserStore.create` -- the plaintext password is never persisted
        or passed to the store."""
        normalized = self._normalize_email(email)
        existing = await self._users.get_by_email(normalized)
        if existing is not None:
            raise EmailAlreadyExists("An account with this email already exists.")
        password_hash = self._passwords.hash(password)
        return await self._users.create(normalized, password_hash, tuple(roles))

    async def login(self, email: str, password: str) -> TokenPair:
        """Verifies credentials and, on success, starts a brand-new
        refresh-token FAMILY (a fresh `family_id`), mints an access +
        refresh token pair in it, persists the refresh token's
        `RefreshRecord`, and returns the pair.

        On failure -- unknown email OR wrong password -- raises
        `InvalidCredentials` identically either way (see that exception's
        own docstring on why). The unknown-email path additionally calls
        `PasswordService.dummy_verify()` before raising, so it costs
        roughly the same wall-clock time as the wrong-password path
        (which calls the real `verify()`) -- an attacker timing this
        endpoint cannot use response latency to tell "no such account"
        apart from "account exists, password wrong"."""
        normalized = self._normalize_email(email)
        user = await self._users.get_by_email(normalized)
        if user is None:
            self._passwords.dummy_verify()
            raise InvalidCredentials("Invalid email or password.")
        if not self._passwords.verify(user.password_hash, password):
            raise InvalidCredentials("Invalid email or password.")
        family_id = uuid.uuid4().hex
        return await self._mint_and_persist(user, family_id)

    async def refresh(self, raw_refresh_token: str) -> TokenPair:
        """THE refresh-token rotation-with-reuse-detection state machine.
        Implements, in this exact order:

        1. `TokenService.decode_refresh` -- structural validation only
           (signature, expiry, issuer, `type == "refresh"`). Invalid on
           any of those grounds -> `InvalidToken`. The decoded claims are
           deliberately NOT otherwise trusted below -- the persisted
           `RefreshRecord` (looked up next, by hash) is the sole source of
           truth for whether this token is still usable; a validly-signed
           JWT whose row says otherwise still loses.
        2. Hash the raw token (`hash_token`) and look it up
           (`RefreshTokenStore.get_by_hash`). **No row** means a validly-
           signed token that this store has never heard of (or no longer
           does) -- forged, or a genuine token from a family/row that's
           been deleted. This does NOT trust the token's own claims to
           revoke anything (there is nothing on file to revoke) --
           just `InvalidToken`.
        3. **`row.revoked`** -> `InvalidToken`. The token's family was
           already killed (by a prior reuse-detection event or a
           `logout()`).
        4. **`row.used_at is not None`** -> **REUSE DETECTED.** This
           exact token was already rotated once before; a second
           presentation of it now can only mean the token was
           compromised (or, less commonly, a client-side race). Calls
           `RefreshTokenStore.revoke_family(row.family_id)` -- revoking
           EVERY row in the family, including whichever token is
           currently the "live" tip of the rotation chain -- then raises
           `TokenReused`. This is deliberately more aggressive than just
           rejecting the reused token: an attacker holding a stolen
           refresh token and a legitimate client both descend from the
           same family, so killing only the reused token would leave
           whichever side currently holds the live rotated token still
           logged in -- which could be the attacker.
        5. **`row.expires_at <= now()`** -> `InvalidToken`. An unused,
           non-revoked row past its own TTL.
        6. **Otherwise, valid:** `RefreshTokenStore.mark_used(row.
           token_hash, now())` (so this exact row can never validate
           again -- see step 4 for why that matters), then mint a NEW
           access token and a NEW refresh token in the SAME family
           (`family_id=row.family_id` -- rotation extends a family, it
           does not start a new one), persist the new refresh token's
           `RefreshRecord`, and return the new `TokenPair`. The just-used
           row is retained with `used_at` set, NOT deleted.

        `TokenReused` and `InvalidToken` both map to `ErrorCode.
        UNAUTHENTICATED` (401) -- see `TokenReused`'s own docstring for
        why a reuse event is deliberately indistinguishable to the client
        from any other refresh failure."""
        # Step 1.
        self._tokens.decode_refresh(raw_refresh_token)

        # Step 2.
        token_hash = hash_token(raw_refresh_token)
        row = await self._refresh_tokens.get_by_hash(token_hash)
        if row is None:
            raise InvalidToken("Refresh token is unknown.")

        # Step 3.
        if row.revoked:
            raise InvalidToken("Refresh token has been revoked.")

        # Step 4.
        if row.used_at is not None:
            await self._refresh_tokens.revoke_family(row.family_id)
            raise TokenReused("Refresh token reuse detected -- the token family has been revoked.")

        # Step 5.
        if row.expires_at <= self._now():
            raise InvalidToken("Refresh token has expired.")

        # Step 6.
        await self._refresh_tokens.mark_used(row.token_hash, self._now())
        user = await self._users.get_by_id(row.user_id)
        if user is None:
            # The row is valid but the user it belongs to is gone (e.g.
            # deleted between mint and refresh) -- there is no principal
            # left to mint a new pair for, so this is an auth failure,
            # not a 500.
            raise InvalidToken("Refresh token no longer maps to an active user.")
        return await self._mint_and_persist(user, row.family_id)

    async def logout(self, raw_refresh_token: str) -> None:
        """Revokes the entire refresh-token family behind
        `raw_refresh_token` -- every token descended from the same login
        stops working, not just this one. Best-effort and idempotent: an
        already-invalid token (malformed, expired, unknown, already
        revoked) does NOT raise -- logging out is not an auth check, and a
        client calling logout with a token that's invalid for any reason
        should still land on "you are logged out", not an error."""
        try:
            self._tokens.decode_refresh(raw_refresh_token)
        except InvalidToken:
            return
        token_hash = hash_token(raw_refresh_token)
        row = await self._refresh_tokens.get_by_hash(token_hash)
        if row is None:
            return
        await self._refresh_tokens.revoke_family(row.family_id)

    async def resolve_access(self, raw_access_token: str) -> AccessClaims:
        """Verifies and decodes an access token, raising `InvalidToken` on
        failure. This is what a framework adapter's
        `get_current_principal` dependency calls on every authenticated
        request's `Authorization: Bearer <token>` header. `async` (even
        though `TokenService.decode_access` itself is synchronous CPU
        work) so this method's signature matches every other
        `AuthService` method and a future revision can add an async check
        (e.g. against a token-blacklist store) without changing the
        interface a framework adapter already depends on."""
        return self._tokens.decode_access(raw_access_token)

    async def _mint_and_persist(self, user: UserRecord, family_id: str) -> TokenPair:
        """Shared by `login` (new family) and `refresh` (existing family,
        rotation) -- mints a fresh access + refresh token pair, persists
        the refresh token's `RefreshRecord`, and returns the pair."""
        access = self._tokens.mint_access(user.id, user.roles)
        refresh_token, refresh_claims = self._tokens.mint_refresh(user.id, family_id)
        record = RefreshRecord(
            token_hash=hash_token(refresh_token),
            jti=refresh_claims.jti,
            family_id=refresh_claims.family_id,
            user_id=user.id,
            issued_at=refresh_claims.issued_at,
            expires_at=refresh_claims.expires_at,
            used_at=None,
            revoked=False,
        )
        await self._refresh_tokens.add(record)
        return TokenPair(access=access, refresh=refresh_token)
