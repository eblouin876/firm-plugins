<!--
block: components/security/auth  # catalog component
last-verified: 2026-07-23
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
needs:
  - PyJWT 2.13.x (tested against 2.13.0): the sole non-stdlib dependency for token minting/verification
  - argon2-cffi 25.1.x (tested against 25.1.0): the sole non-stdlib dependency for password hashing
  - app-level wiring (NOT part of this component): UserStore/RefreshTokenStore implementations against a real ORM/session, AuthService construction with a real signing key/TTLs at app startup, and an app exception handler using this component's own AUTH_ERROR_HTTP table to map onto ErrorEnvelope/ErrorCode -- see backend/fastapi's app/core/security/auth/stores.py + app/main.py for the reference implementation (Stage 5a, #41), and backend/django's core/security/auth/stores.py for the Django equivalent (Stage 5b, #44)
exposes:
  - PasswordService (hash, verify, needs_rehash, dummy_verify), TokenService (mint_access, mint_refresh, decode_access, decode_refresh), AuthService (register, login, refresh, logout, resolve_access) -- in _core.py
  - UserStore / RefreshTokenStore (Protocols), UserRecord / RefreshRecord (frozen dataclasses), hash_token(raw) -- the storage seam a framework adapter implements
  - TokenPair, AccessClaims, RefreshClaims -- the claim/result shapes
  - AuthError hierarchy: InvalidCredentials, InvalidToken, TokenReused, EmailAlreadyExists, InvalidSingleUseToken -- each documents the ErrorCode it maps to
  - bearer_scheme, build_get_current_principal, require_roles, AUTH_ERROR_HTTP -- the FastAPI wiring, in fastapi.py (Stage 5a, #41)
  - resolve_principal, require_roles, InsufficientRole, AUTH_ERROR_HTTP -- the Django wiring, in django.py (Stage 5b, #44)
  - AccountService (request_email_verification, verify_email, request_password_reset, reset_password) -- email verification + password reset, composed ALONGSIDE AuthService, not a subclass -- in _core.py (Stage 5c, #45)
  - SingleUseTokenService (issue, consume) / SingleUseTokenStore (Protocol) / SingleUseTokenRecord -- the hashed, single-use verify/reset token seam AccountService runs against
  - LockoutPolicy (is_locked, record_failure, clear) / LockoutStore (Protocol) / AttemptRecord -- per-account failed-login lockout, optionally shared between AuthService.login and AccountService.reset_password
  - EmailSender (Protocol) / EmailMessage / ConsoleEmailSender -- the email-delivery seam AccountService sends verify/reset links through; ConsoleEmailSender is DEV-ONLY (logs the raw token instead of delivering it)
  - AuthEventSink (Protocol) -- the optional audit-event seam AuthService.login and every AccountService method emit through
  - its co-located doc fragment: docs/fragment.md
-->

# auth

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A framework-neutral auth core: Argon2id password hashing, PyJWT HS256
access/refresh tokens, and an `AuthService` orchestrator implementing
register/login/refresh/logout — including single-use refresh-token
ROTATION with REUSE DETECTION, the security-critical piece of this
component. Embodies `references/security/secure-baseline.md`'s
"Authentication & authorization" section (password hashing with a strong
adaptive algorithm; tokens validated fully — signature, expiry, issuer;
short-lived access tokens with refresh over long-lived static tokens).
Lives at `templates/components/security/auth/` in this repo; a Stage 5a
(#41) backend block copies `_core.py` + `fastapi.py` into
`app/core/security/auth/`.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block.

**This component ships `_core.py` + `fastapi.py` + `django.py`.**
`fastapi.py` (Stage 5a, #41) is pure framework glue over `_core.py` — the
`HTTPBearer` scheme, a `build_get_current_principal` dependency FACTORY
(takes the app's own `get_auth_service` provider, since this component has
no DB session/settings of its own to build one from), `require_roles`, and
the `AUTH_ERROR_HTTP` exception -> `(status, ErrorCode string)` table —
with **zero `app.*` import**, matching `_core.py`'s own "zero FastAPI/
Django/SQLAlchemy import" posture in reverse (see `fastapi.py`'s own
module docstring). `django.py` (Stage 5b, #44) is the same idea for
Django/DRF — `resolve_principal(request, auth_service)` (an awaited
helper, not a `Depends()`-style factory, since Django/DRF has no
equivalent auto-invoked injection point), `require_roles(request,
auth_service, *roles)`, `InsufficientRole`, and the identically-shaped
`AUTH_ERROR_HTTP` table — with the same **zero project import** posture
(no `core.*`/`app.*`, and deliberately no `rest_framework` import either,
so a plain-Django project without DRF can use it too; see `django.py`'s
own module docstring). Vendoring these files is still NOT the whole wiring
job: `UserStore`/`RefreshTokenStore` implementations against a real ORM,
`AuthService` construction with real secrets/TTLs at app startup, real
route handlers, and an app-level exception handler for the `AuthError`
base class are all APP code (they import the app's own models/settings),
never part of this vendored component — see `backend/fastapi`'s
`app/core/security/auth/stores.py` + `app/main.py`'s `_auth_error_handler`
for the FastAPI reference implementation, and `backend/django`'s
`core/security/auth/stores.py` for the Django equivalent. Zero FastAPI,
Django, or SQLAlchemy import exists anywhere in `_core.py` — verified by
this component's own `tests/`, which import and exercise `_core.py`
completely standalone.

## Contents
- Composition contract
- Password hashing: Argon2id + the timing-defense `dummy_verify()`
- Tokens: PyJWT HS256, injected clock, and why expiry isn't PyJWT's own check
- Refresh-token storage: SHA-256 hash, never the raw token
- The refresh-rotation state machine (the security-critical core)
- Account lifecycle: email verification, password reset, lockout (Stage 5c, #45)
- Exception hierarchy → ErrorCode mapping (for the framework adapter)
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **PyJWT 2.13.x** (tested against the exact pin **2.13.0**) — the only
  dependency `TokenService` needs. Not yet added to
  `references/compatibility-matrix.md`'s Backend — Python row; the agent
  that wires this component into the FastAPI or Django backend block
  owns adding that pin (and `argon2-cffi`'s, below) to the matrix and to
  that block's `pyproject.toml`, landing the dependency pin next to the
  code that first actually consumes it in a running backend.
- **argon2-cffi 25.1.x** (tested against the exact pin **25.1.0**) — the
  only dependency `PasswordService` needs. Same matrix caveat as above.
- **App-level wiring** (not part of this component, even with `fastapi.py`
  vendored) — implements `UserStore` and `RefreshTokenStore` against a
  real ORM/session, constructs `TokenService`/`AuthService` with a real
  signing key (from secrets-loading, never hardcoded) and real TTLs at
  app startup, wires real route handlers, and registers an app exception
  handler for the `AuthError` base class that renders `fastapi.py`'s own
  `AUTH_ERROR_HTTP` table as `error-envelope/`'s `ErrorEnvelope`/
  `ErrorCode`. See "Exception hierarchy → ErrorCode mapping" below for
  the exact mapping, and `backend/fastapi`'s `app/core/security/auth/
  stores.py` for a concrete implementation.

**EXPOSES** (`_core.py` unless noted)
- `PasswordService` — `hash(password) -> str`, `verify(stored_hash,
  password) -> bool`, `needs_rehash(stored_hash) -> bool`,
  `dummy_verify() -> None` (user-enumeration timing defense — see below).
- `TokenService(signing_key, *, issuer, access_ttl, refresh_ttl, now)` —
  `mint_access(sub, roles) -> str`, `mint_refresh(sub, family_id) ->
  tuple[str, RefreshClaims]`, `decode_access(token) -> AccessClaims`,
  `decode_refresh(token) -> RefreshClaims`.
- `AuthService(users, refresh_tokens, passwords, tokens, now)` —
  `register(email, password, roles=()) -> UserRecord`, `login(email,
  password) -> TokenPair`, `refresh(raw_refresh_token) -> TokenPair` (THE
  rotation state machine), `logout(raw_refresh_token) -> None`,
  `resolve_access(raw_access_token) -> AccessClaims`.
- `UserStore` / `RefreshTokenStore` — `Protocol`s a framework adapter
  implements; `UserRecord` / `RefreshRecord` — the frozen dataclasses
  they operate on; `hash_token(raw) -> str` — the SHA-256 helper the
  refresh store's rows are keyed by.
- `TokenPair`, `AccessClaims`, `RefreshClaims` — the result/claim shapes.
- `AuthError` and its subclasses `InvalidCredentials`, `InvalidToken`,
  `TokenReused`, `EmailAlreadyExists`, `InvalidSingleUseToken` — see the
  mapping section below.
- **Stage 5c (#45)**: `AccountService(users, tokens, email, passwords,
  refresh_tokens, now, *, events=None, lockout=None, frontend_base_url,
  verify_ttl=24h, reset_ttl=1h)` — `request_email_verification(user) ->
  None`, `verify_email(raw_token) -> None`, `request_password_reset(
  email) -> None` (never raises), `reset_password(raw_token,
  new_password) -> None`; `SingleUseTokenService(store, now)` —
  `issue(user_id, purpose, ttl) -> str` (raw token), `consume(raw,
  purpose) -> str` (user id); `SingleUseTokenStore` (Protocol) /
  `SingleUseTokenRecord`; `LockoutPolicy(store, *, max_failures,
  lockout_duration, window, now)` — `is_locked`, `record_failure`,
  `clear`; `LockoutStore` (Protocol) / `AttemptRecord`; `EmailSender`
  (Protocol) / `EmailMessage` / `ConsoleEmailSender` (DEV-ONLY); and
  `AuthEventSink` (Protocol) — see "Account lifecycle" below.
- **`fastapi.py`**: `bearer_scheme` (an `HTTPBearer(auto_error=False)`
  instance), `build_get_current_principal(get_auth_service) ->
  <dependency>` (a dependency FACTORY — takes the app's own per-request
  `AuthService` provider, returns a dependency resolving a bearer token to
  `AccessClaims`), `require_roles(get_current_principal, *roles) ->
  <dependency>` (role-gated dependency factory; RBAC's wire surface is
  Stage 5d — this just enforces `AccessClaims.roles` membership),
  `InsufficientRole` (a component-level exception mapping to the existing
  `permission_denied`/403 — no new `ErrorCode` invented), and
  `AUTH_ERROR_HTTP` (the exception-type -> `(status, ErrorCode string)`
  table an app's own exception handler consults).
- **`django.py`**: `resolve_principal(request, auth_service) ->
  AccessClaims` (an awaited helper, not a dependency factory — see
  `django.py`'s own module docstring on why Django/DRF has no `Depends()`
  equivalent to compose against), `require_roles(request, auth_service,
  *roles) -> AccessClaims` (resolves the principal AND enforces role
  membership in one awaited call), `InsufficientRole` (the same
  `permission_denied`/403 mapping as `fastapi.py`'s own, kept as a
  separate class per adapter so each file still reads standalone when
  vendored alone), and `AUTH_ERROR_HTTP` (identically shaped to
  `fastapi.py`'s own table).
- Its co-located doc fragment: `docs/fragment.md`.

## Password hashing: Argon2id + the timing-defense `dummy_verify()`

`PasswordService` wraps `argon2.PasswordHasher`, left at Argon2id
(argon2-cffi's own default `Type.ID`) and its library-default cost
parameters — already OWASP's recommended default for new applications,
resistant to both GPU-parallel cracking and timing/cache side-channels
in ways the pure Argon2i/Argon2d variants aren't. A tuned
`argon2.PasswordHasher` instance can be passed into the constructor for a
project that wants to raise/lower the cost parameters for its own
hardware budget.

`verify()` collapses both a wrong password (`VerifyMismatchError`) and a
corrupt/foreign-format stored hash (`InvalidHashError`) to the same
`False` — the caller must never be able to tell those two apart through
the return value. Any OTHER exception is NOT caught and propagates,
deliberately — silently turning an unexpected bug into "verification
failed" would hide a real misconfiguration behind an ordinary-looking
failed login.

**`dummy_verify()`** exists purely as a user-enumeration timing defense.
`AuthService.login` calls it on the "no such email" path before raising
`InvalidCredentials`, so that path costs the same wall-clock time (one
Argon2id verify) as the "email found, password checked" path. Without
this, Argon2id's own deliberate slowness becomes the leak: an attacker
timing the login endpoint could tell a registered email from an
unregistered one purely by which response came back faster.

## Tokens: PyJWT HS256, injected clock, and why expiry isn't PyJWT's own check

`TokenService` mints and verifies HS256 JWTs against one shared
`signing_key`. Every claim listed in the component header's EXPOSES
section is present on every token (`sub`, `type`, `iat`, `exp`, `iss`,
`jti`, plus `roles` on access tokens / `fid` on refresh tokens);
`algorithms=["HS256"]` is passed explicitly on every decode call (never
inferred from the token's own header — trusting a token to name its own
verification algorithm is a known JWT vulnerability class), and the
`type` claim is asserted to match what the caller asked for — an access
token presented as a refresh token, or vice versa, is rejected at that
check.

**Expiry is verified manually against the injected `now()`, not PyJWT's
own built-in exp check** (`verify_exp`/`verify_iat` are explicitly turned
off in the `jwt.decode` call). PyJWT's own expiry validation always
compares against the real system clock with no parameter to substitute a
different "now" — which would make this component's own tests (advance
an injected clock past a TTL, assert rejection) either race the real
clock or be entirely disconnected from the `now` a given `TokenService`
was actually constructed with. Checking expiry by hand, against the
exact same `now` callable every other part of `TokenService`/
`AuthService` uses, is what makes `tests/test_core.py`'s expiry
assertions fully deterministic — no `time.sleep`, no wall-clock races.
A framework adapter should pass a real callable (e.g. `lambda:
datetime.now(timezone.utc)`) in production; tests pass an injectable,
advanceable fake (see `tests/conftest.py`'s `Clock`).

## Refresh-token storage: SHA-256 hash, never the raw token

`hash_token(raw) -> str` is `hashlib.sha256(raw.encode()).hexdigest()` —
the ONLY form of a refresh token this module ever persists. A fast
cryptographic hash (not a slow password KDF like Argon2/bcrypt) is the
correct choice HERE, deliberately different from `PasswordService`
above: a password is a low-entropy human-chosen secret vulnerable to
offline brute force against a stolen hash, which a slow KDF specifically
defends against. A refresh token is a high-entropy value this module
itself generated (a signed JWT — effectively random to an attacker) —
brute-forcing a SHA-256 preimage of 256 bits of entropy is infeasible
regardless of hash speed, so a slow KDF here would only add CPU cost to
every refresh/logout call for zero additional security. Hashing at all
still matters: a read-only compromise of the store's rows (a leaked
backup, a compromised read replica) does not hand out live, directly
usable refresh tokens.

## The refresh-rotation state machine (the security-critical core)

`AuthService.refresh(raw_refresh_token)` implements, in this exact
order — see `_core.py`'s own docstring on this method for the full
detail:

1. `TokenService.decode_refresh` — structural validation only
   (signature, expiry, issuer, `type == "refresh"`). Invalid → `InvalidToken`.
2. Hash the token, look up the row (`RefreshTokenStore.get_by_hash`). **No
   row** → `InvalidToken` — deliberately does NOT trust the token's own
   claims to revoke anything, since there's nothing on file to revoke.
3. **`row.revoked`** → `InvalidToken`.
4. **`row.used_at is not None`** → **REUSE DETECTED.** Calls
   `revoke_family(row.family_id)` — killing EVERY token in the family,
   including whichever one is currently the live tip of the rotation
   chain — then raises `TokenReused`.
5. **`row.expires_at <= now()`** → `InvalidToken`.
6. **Otherwise valid:** `mark_used(row.token_hash, now())`, mint a NEW
   access + refresh pair in the SAME family, persist the new refresh
   record, return the new pair. The just-used row is RETAINED with
   `used_at` set — not deleted — because that retention is exactly what
   makes step 4 able to detect a second presentation as reuse rather
   than "not found".

The persisted `RefreshRecord`, never the JWT's own claims, is the sole
source of truth for whether a refresh token is still usable — a
validly-signed, unexpired JWT whose row says otherwise still loses.

## Account lifecycle: email verification, password reset, lockout (Stage 5c, #45)

`AccountService` is composed ALONGSIDE `AuthService` — constructed and
used independently, not a subclass, not required to touch `AuthService`
at all — against the same underlying `UserStore`/`RefreshTokenStore` (and,
optionally, `LockoutStore`) a project wires both services from. Three new
seams support it, each with exactly one shipped implementation
(`ConsoleEmailSender`) or none (`SingleUseTokenStore`/`LockoutStore`/
`AuthEventSink` are pure `Protocol`s a framework adapter implements):

- **Single-use tokens** (`SingleUseTokenService`). `issue(user_id,
  purpose, ttl)` mints a `secrets.token_urlsafe(32)` raw token (~256 bits
  of CSPRNG entropy), persists only its SHA-256 hash (`hash_token` — the
  SAME fast-hash-not-a-slow-KDF reasoning `RefreshRecord` already
  documents: a high-entropy, module-generated value, not a low-entropy
  human-chosen secret), and returns the raw token. `consume(raw,
  purpose)` looks it up by hash and raises `InvalidSingleUseToken` for
  ANY of: unknown hash, already-used (`used_at` set — the row is RETAINED
  on consumption, exactly `RefreshRecord`'s "retain, don't delete"
  posture, so a second presentation is recognized as reuse), expired, or
  a `purpose` mismatch (a `"verify"` token presented to a reset flow, or
  vice versa) — all four collapse to the SAME exception and message,
  mirroring `InvalidCredentials`'/`TokenReused`'s own "don't leak which
  specific reason" posture.
- **Lockout** (`LockoutPolicy`). Pure counting/threshold logic over
  `LockoutStore`'s dumb persistence: `max_failures` consecutive failures
  for one `account_key` within a rolling `window` locks it for
  `lockout_duration` (re-armed on every subsequent failure while still
  locked). `AuthService.login`'s OPTIONAL `lockout=` parameter (`None` by
  default — every prior behavior is unchanged unless a project passes
  one) consults it BEFORE spending a real Argon2id verify on a locked
  account, and `AccountService.reset_password` — if given the SAME
  `LockoutPolicy` (or at least one built against the same underlying
  store) — clears it on a successful reset, so a user who tripped
  lockout guessing, then reset their password, isn't left blocked for the
  remaining cooldown despite now holding the correct password. A
  deliberately-accepted non-atomic read-modify-write relaxation (see
  `LockoutPolicy`'s own docstring) — at absolute worst it delays exactly
  when a lock becomes visible by a small, bounded amount; it can NEVER
  let a wrong password succeed.
- **Email** (`EmailSender` / `EmailMessage`). `AccountService` builds a
  plain-text `EmailMessage` (never HTML — no templating/injection
  surface) with a link containing the raw token in the URL **fragment**
  (`{frontend_base_url}/verify-email#token=<raw>` /
  `.../reset-password#token=<raw>`) — deliberately never a query string,
  since a fragment is never sent to the server and is typically excluded
  from `Referer` headers and access/proxy logs, keeping a single-use,
  bearer-credential-equivalent token out of exactly the places a query
  string routinely ends up. `ConsoleEmailSender` (the one shipped
  implementation) logs the message, INCLUDING the raw token — **DEV/TEST
  ONLY**; a project's own environment branch (never anything in this
  component) is what must ensure it's never constructed in production. A
  real implementation (SMTP, SES, Postmark, ...) is application/
  infrastructure code, not part of this framework-neutral core — see
  `backend/fastapi`'s `app/core/security/auth/stores.py:
  get_email_sender()` for a reference `SmtpEmailSender`.
- **`request_password_reset(email)` never raises and never reveals
  account existence** — the caller (an HTTP route) always returns the
  SAME response either way (a project's own 202-always convention — see
  `backend/fastapi`'s `POST /auth/request-password-reset`), extending
  `InvalidCredentials`'s user-enumeration defense to the "forgot
  password" flow, historically an even more common enumeration vector
  than login itself.
- **`reset_password` revokes EVERY refresh-token family the user has**
  (`RefreshTokenStore.revoke_all_for_user`, added alongside
  `revoke_family` specifically for this) — every device/session logged
  out, not just the one that requested the reset, since whatever was true
  about the account's security under the OLD password can no longer be
  assumed once it's been reset.
- **`AuthEventSink`** (optional on both services, `None` by default) lets
  a project emit `auth.login`, `auth.lockout.triggered`,
  `auth.email.verify_requested`/`verified`/`verify_failed`,
  `auth.password.reset_requested`/`completed`/`failed` without this
  module importing an audit-logging component directly — a thin adapter
  forwards `emit(action, *, actor, outcome, **extra)` to whatever a
  project's own audit sink expects (see `backend/fastapi`'s
  `AuditAuthEventSink`).

## Exception hierarchy → ErrorCode mapping (for the framework adapter)

This module raises its OWN exceptions rather than importing
`error-envelope/`'s `AppError`/`ErrorCode` directly — keeping `_core.py`
importable with zero framework/app-layer dependencies. A framework
adapter's exception handler maps each one onto that LOCKED, closed enum
(which this component does NOT extend):

| `_core.py` exception | Maps to `ErrorCode` | HTTP status |
| --- | --- | --- |
| `InvalidCredentials` | `unauthenticated` | 401 |
| `InvalidToken` | `unauthenticated` | 401 |
| `TokenReused` | `unauthenticated` | 401 (same as `InvalidToken` — see below) |
| `EmailAlreadyExists` | `conflict` | 409 |
| `InvalidSingleUseToken` | `unauthenticated` | 401 (same generic shape — see "Account lifecycle" above) |

`TokenReused` and `InvalidToken` deliberately map to the SAME code and
the same generic message on the wire — a client (attacker or otherwise)
holding a stolen-but-already-rotated refresh token must not be able to
distinguish "reuse was detected and your whole session was just killed"
from "this token was simply invalid," since that distinction would
confirm reuse detection exists and just fired. A framework adapter that
wants reuse events flagged for a human should log `TokenReused`
specifically (an audit-logging component, e.g. `security/audit-logging/`
in this catalog, is the right place for that signal) — never surface it
differently on the response body/status than any other auth failure.

## Testing

`tests/test_core.py` (54 tests) covers: `PasswordService` (hash≠
plaintext, verify true/false, malformed-hash handling, `needs_rehash`
false-on-fresh/true-after-a-parameter-change, `dummy_verify` never
raising); `TokenService` (access/refresh round-trip, unique `jti` per
mint, tampered signature rejected, expired access AND refresh tokens
rejected via the injected clock, valid-right-up-to-the-ttl-boundary,
wrong secret rejected, issuer mismatch rejected, access-as-refresh and
refresh-as-access both rejected, malformed token strings rejected,
empty-signing-key construction rejected, `hash_token`'s determinism/
uniqueness/hex-format); `AuthService.register` (creates a user, duplicate
email raises, email normalization on both write and lookup, roles
stored); `AuthService.login` (success returns a usable pair, unknown
email raises `InvalidCredentials` while ACTUALLY exercising
`dummy_verify()` — asserted via a spy, wrong password raises the SAME
exception type+message as unknown email, a refresh record is persisted
on success); and — the crown jewel — `AuthService.refresh`'s full state
machine: happy-path rotation (new pair differs, old row's `used_at` set,
new row present and unused, same family), **reuse detection revoking the
entire family including the just-minted valid child** (the load-bearing
regression test), refresh against an already-revoked family, an unknown-
but-validly-signed token (asserting `revoke_family` was NOT called),
expired rows, a multi-hop rotation chain staying in one family, and
type-confusion (an access token presented to `refresh()`); plus
`AuthService.logout` (revokes the family, subsequent refresh with any
family token fails, idempotent, a garbage/unknown/access token doesn't
raise); and `AuthService.resolve_access` (valid returns claims with
roles, invalid/wrong-type/expired all raise `InvalidToken`).

Run:
```
uv run --python 3.13 --with pyjwt==2.13.0 --with argon2-cffi==25.1.0 --with pytest --with pytest-asyncio -- \
  pytest templates/components/security/auth/tests/ -q
```
(async tests use explicit `@pytest.mark.asyncio` markers — pytest-asyncio's
default "strict" mode picks them up with no extra `--asyncio-mode` flag or
ini configuration needed, matching this catalog's `db-session` component.)

## Judgment calls

- **Shipped `_core.py` alone first, `fastapi.py` in a separate follow-up
  commit, `django.py` deferred a further stage still — not all three
  (`_core.py`+`fastapi.py`+`django.py`) in one commit like every other
  dual-framework component in this catalog (`rate-limiting/`,
  `security-headers/`, ...).** This component's core is unusually
  security-sensitive (Stage 5a's whole point was proving the
  reuse-detection state machine exhaustively in isolation before any
  framework code touched it) — splitting "prove the core is correct" from
  "wire a FastAPI adapter" into two pieces of work was judged the right
  call specifically for this component. `django.py` landed a full stage
  later still (Stage 5b, #44) — until then, a project on the Django track
  could vendor `_core.py` only, implementing its own adapter by hand, same
  as any other catalog component before its second framework lands.
  `django.py`'s own shape deliberately mirrors `fastapi.py`'s (same
  `AUTH_ERROR_HTTP` table, same `InsufficientRole`/role-membership
  semantics) even though its mechanics differ (awaited helper functions,
  not `Depends()`-composed dependencies) — see `django.py`'s own module
  docstring for that mechanical difference and why it doesn't change what
  either adapter actually enforces.
- **Expiry checked by hand against an injected `now`, not PyJWT's
  built-in `verify_exp`.** See "Tokens" above — PyJWT has no parameter to
  substitute a fake "current time" into its own exp/iat validation, so
  relying on it would make this component's expiry tests either flaky
  (racing the real system clock) or untestable without real sleeps. Both
  `TokenService` and `AuthService` take the SAME injected `now` for this
  reason — a framework adapter should pass one shared callable to both.
- **A fast hash (SHA-256), not a KDF, for refresh tokens.** See "Refresh-
  token storage" above — the entropy source differs fundamentally from a
  human-chosen password, so the threat a slow KDF defends against
  (offline brute force of a low-entropy secret) doesn't apply here, and
  paying Argon2id's cost on every refresh call would be pure overhead.
- **`TokenReused` is a distinct exception type from `InvalidToken`, but
  maps to the identical wire response.** Keeping them as separate Python
  exception TYPES (rather than one `InvalidToken` with a `reused: bool`
  flag) lets a framework adapter's exception handler branch internally —
  e.g. to write a distinct audit-log entry for reuse specifically — while
  still rendering the exact same `ErrorEnvelope`/401 on the wire either
  way. Collapsing them into one exception type would make that internal
  branching (log differently, respond identically) awkward without an
  extra flag; keeping the flag out of the type and out of the response
  keeps the wire contract simple while the Python-level distinction stays
  available to whoever wants it server-side.
- **Reuse revokes the WHOLE family, not just the reused token.** An
  attacker holding a stolen refresh token and the legitimate client both
  descend from the same family by the time reuse is detected — revoking
  only the specific token that got reused would still leave whichever
  side currently holds the live, rotated-forward token logged in, which
  could be the attacker. Full-family revocation forces BOTH sides back
  through a real login, the only response that can't leave an attacker
  quietly still authenticated.
- **`register`/`login` normalize email via `.strip().lower()`, applied
  identically at both write and lookup time.** Without this, a
  case/whitespace variant of an existing email (`"Alice@Example.com "`)
  could register as a distinct account even though most mail providers
  deliver it to the same inbox as the canonical form — a real account-
  confusion/duplicate-account footgun, not just a cosmetic one.
