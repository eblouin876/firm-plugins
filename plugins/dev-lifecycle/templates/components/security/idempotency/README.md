<!--
block: components/security/idempotency  # catalog component
last-verified: 2026-07-22
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
needs:
  - starlette/fastapi (via the project's FastAPI install): the middleware in fastapi.py
  - django (5.2.x): the middleware in django.py
  - a shared store for multi-process/multi-replica deployments (optional, Stage 11): InMemoryIdempotencyStore is per-process only, and does not reserve across the request lifecycle -- see Judgment calls
  - an authentication layer that runs BEFORE this middleware and populates a principal (e.g. request.state.user_id / request.user): principal_getter is required -- see "Principal scoping"
exposes:
  - IdempotencyStore (Protocol), InMemoryIdempotencyStore, RedisIdempotencyStore (Stage 11 stub, never imports redis), IdempotencyRecord, StoredResponse, IdempotencyOutcome, REPLAY_HEADER_DENYLIST, validate_key(raw_key), compute_fingerprint(method, path, raw_body), compute_storage_key(principal, idempotency_key), strip_non_replayable_headers(headers), check(store, key, fingerprint), record_response(store, key, fingerprint, response, *, now=None) -- in _core.py
  - InvalidIdempotencyKeyError, IdempotencyConflictError
  - fastapi.py: IdempotencyMiddleware, add_idempotency(app, *, store, principal_getter, header_name="Idempotency-Key")
  - django.py: IdempotencyMiddleware (settings-configurable: IDEMPOTENCY_HEADER_NAME, IDEMPOTENCY_PRINCIPAL_GETTER), default_principal_getter(request)
  - its co-located doc fragment: docs/fragment.md
-->

# idempotency

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: `Idempotency-Key` extraction/
validation, a method+path+body-hash fingerprint, and a PRINCIPAL-SCOPED
storage key in `_core.py`, a buffering `BaseHTTPMiddleware` in `fastapi.py`,
and a Django `MIDDLEWARE` class in `django.py` — both replaying a
first-seen response verbatim for a genuine retry, and returning `409` for
the same key reused on a different request. Embodies
`references/security/payments-security.md`'s "Idempotency keys" section: a
retried request (network blip, client double-submit) must never
double-charge. Lives at `templates/components/security/idempotency/` in
this repo; Stage 3-4 backend blocks copy the whole directory into
`app/core/security/idempotency/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- The key/fingerprint/replay model
- Principal scoping: why, and the required `principal_getter`
- Header replay: what's stripped, and why
- FastAPI: why BaseHTTPMiddleware here (unlike the sibling components)
- Django: settings and the header-name mapping
- Non-cacheable server errors
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Starlette/FastAPI** (via the project's FastAPI install) — the
  `IdempotencyMiddleware` in `fastapi.py`.
- **Django 5.2.x** — the `IdempotencyMiddleware` in `django.py`.
- **A shared store for multi-process/multi-replica deployments (optional,
  Stage 11)** — `InMemoryIdempotencyStore` is per-process only and does not
  reserve across the request lifecycle; see "Judgment calls".
- **An authentication layer that runs BEFORE this middleware** — this
  middleware requires a `principal_getter` (a callable resolving the
  caller's identity from the request), and that identity has to already be
  populated by the time this middleware runs. See "Principal scoping".

**EXPOSES**
- `IdempotencyStore` (Protocol), `InMemoryIdempotencyStore`,
  `RedisIdempotencyStore` (a Stage 11 stub that raises `NotImplementedError`
  on construction and never imports `redis`), `IdempotencyRecord`,
  `StoredResponse`, `IdempotencyOutcome`, `REPLAY_HEADER_DENYLIST`,
  `validate_key(raw_key)`, `compute_fingerprint(method, path, raw_body)`,
  `compute_storage_key(principal, idempotency_key)`,
  `strip_non_replayable_headers(headers)`, `check(store, key, fingerprint)`,
  `record_response(store, key, fingerprint, response, *, now=None)` — all in
  `_core.py`.
- `InvalidIdempotencyKeyError`, `IdempotencyConflictError` — both subclass
  `IdempotencyError`.
- `fastapi.py`: `IdempotencyMiddleware`, `add_idempotency(app, *, store,
  principal_getter, header_name="Idempotency-Key")` (one-line wiring;
  `principal_getter` is required, no default).
- `django.py`: `IdempotencyMiddleware` (settings-configurable:
  `IDEMPOTENCY_HEADER_NAME`, default `"HTTP_IDEMPOTENCY_KEY"`;
  `IDEMPOTENCY_PRINCIPAL_GETTER`, a required dotted import path when
  `principal_getter` isn't passed as a constructor kwarg),
  `default_principal_getter(request)` (the ready-to-use common-case
  implementation).
- Its co-located doc fragment: `docs/fragment.md`.

## Principal scoping: why, and the required `principal_getter`

**The storage key is never the raw client-supplied `Idempotency-Key`
alone.** A client fully controls that header's value. If it were used
directly as the storage lookup key, one authenticated caller could supply
the SAME key a different caller (or a different one of their own future
requests) happens to use, and receive THAT request's stored response
verbatim — a cross-principal response replay, potentially handing one
user another user's payment confirmation, order contents, or session
cookie. `compute_storage_key(principal, idempotency_key)` composes a
principal identifier into the key BEFORE anything reaches
`IdempotencyStore.get()`/`.put()`, so two different principals using the
identical `Idempotency-Key` value land in two independent namespaces.

Both `IdempotencyMiddleware`s take a **required** `principal_getter`
callable — `(request) -> str | None`, resolving the caller's identity from
the request (e.g. `request.state.user_id` after an auth middleware
populates it, or `django`'s `request.user.pk`). There is no default that
means "no principal" — that would silently reopen the exact bug this
section describes. FastAPI: pass it directly, there is no other resolution
path. Django: pass it directly, or set `IDEMPOTENCY_PRINCIPAL_GETTER` in
`settings.py` to a dotted import path (Django's own convention for a
settings value naming a callable) — `django.py` ships
`default_principal_getter` as the ready-to-use common case (authenticated
`request.user.pk`, `None` for anonymous).

**This middleware MUST run AFTER authentication.** `principal_getter`
reads request state an earlier middleware/dependency populates — if this
middleware runs before auth, `principal_getter` sees an unauthenticated
request on every call and the anonymous policy (below) applies to
everything, defeating the scoping entirely. FastAPI: register this
middleware's `add_middleware()` call BEFORE any auth middleware's (Starlette
runs middleware in reverse-of-registration order on the request path, so
registering this one first means it executes last, i.e. after auth runs).
Django: list this middleware AFTER
`"django.contrib.auth.middleware.AuthenticationMiddleware"` in
`MIDDLEWARE` (Django runs `MIDDLEWARE` top-to-bottom on the request path).

**Anonymous-request policy: default DENY (passthrough), never a shared
namespace.** If `principal_getter(request)` returns `None`/empty, this
middleware treats the request EXACTLY as if it had no `Idempotency-Key`
header at all — full passthrough, no dedup, no replay, no storage write.
This is a deliberate fail-closed default: an anonymous request has no
stable identity to scope a storage key to, and falling back to one shared
"anonymous" namespace would reintroduce cross-client replay for every
unauthenticated caller. A project that genuinely needs idempotency
protection on unauthenticated traffic (e.g. an unauthenticated checkout
flow) opts in EXPLICITLY, in its own `principal_getter`, by falling back to
a per-client namespace instead of `None` — e.g.
`lambda request: request.state.user_id or f"anon-ip:{request.client.host}"`
— never a single fixed string shared by every anonymous caller.

## Header replay: what's stripped, and why

`record_response()` strips `REPLAY_HEADER_DENYLIST` from a response's
headers before persisting it: `Set-Cookie`, `WWW-Authenticate`,
`Proxy-Authenticate`, `Authorization`. These are per-exchange or
per-session values that must never be replayed onto a later
request/response — most importantly `Set-Cookie`: replaying the FIRST
caller's session cookie onto a LATER response would hand out session
material outside its intended recipient. Every other header (e.g.
`Content-Type`) replays unchanged. This stripping happens once, in
`record_response()`, so a store implementation (in-memory today, Redis in
Stage 11) never has to apply this policy itself.

## The key/fingerprint/replay model

Every request is inspected for an `Idempotency-Key` header. **No header,
no effect** — unlike security-headers/CORS/rate-limiting's always-on
posture, this component is opt-in per request, matching
payments-security.md's guidance to pass a key on every payment-mutating
request rather than a blanket policy every route must carry.

When the header is present:
1. `validate_key()` checks it: non-empty, at most `MAX_KEY_LENGTH` (255)
   characters, and restricted to a safe charset (letters, digits, `-`, `_`,
   `.`). A key failing this returns `400`.
2. `compute_fingerprint(method, path, raw_body)` hashes what this key was
   actually used FOR — the HTTP method, the request path (no query
   string), and a SHA-256 of the exact raw request body bytes (never a
   parsed/re-serialized body, same rationale as webhook-signature's raw-body
   requirement).
3. `check()` looks the key up in the store:
   - **Not found** → proceed: the middleware calls the downstream handler.
   - **Found, same fingerprint** → **replay**: the stored response is
     returned verbatim, the handler never runs again.
   - **Found, different fingerprint** → **conflict**: `409`, the same key
     was reused for a materially different request (different method,
     path, or body). The handler never runs.
4. On a fresh (non-replay) request, once the handler produces a response,
   `record_response()` persists it — but only if the status is not a
   server error; see "Non-cacheable server errors" below.

## FastAPI: why `BaseHTTPMiddleware` here (unlike the sibling components)

security-headers and rate-limiting are deliberately pure-ASGI to avoid
`BaseHTTPMiddleware`'s response-body buffering. This component does the
opposite on purpose: its entire job is capturing and later replaying a
**complete** response body, so the buffering `BaseHTTPMiddleware` performs
is exactly the work needed, not overhead to avoid. See "Judgment calls".

## Django: settings and the header-name mapping

`IDEMPOTENCY_HEADER_NAME` in `settings.py` (default
`"HTTP_IDEMPOTENCY_KEY"`) is the Django `META` key form, not the raw HTTP
header name — Django maps `Idempotency-Key` to `HTTP_IDEMPOTENCY_KEY`
(uppercase, hyphens to underscores, `HTTP_` prefix), matching
webhook-signature/django.py's identical `header_name` convention. Add
`"app.core.security.idempotency.django.IdempotencyMiddleware"` to
`MIDDLEWARE`.

## Non-cacheable server errors

A response with a `5xx` status is **never** recorded — it's presumed
transient (a timeout, a downstream outage), not a deterministic outcome of
the request itself. Caching it would mean a legitimate retry after a
transient failure gets permanently denied a real attempt, replaying the
same 500 forever. `2xx`–`4xx` responses ARE cached: they're deterministic
outcomes of this exact request (including a validation error — retrying
the identical bad request should get the identical validation error, not
re-run the handler's side effects again).

## Testing

`tests/test_core.py` covers every `validate_key()` rejection path (missing,
overlong, unsafe character) and that the rejection message never echoes the
raw key; `compute_fingerprint()`'s determinism and sensitivity to method/
path/body; `check()`/`record_response()`'s replay and conflict outcomes,
including that the conflict error never echoes the key or either
fingerprint; storage isolation (different keys in one store, and two
separate store instances not sharing state); that `RedisIdempotencyStore`
raises `NotImplementedError` on construction with `redis` never imported;
`compute_storage_key()`'s determinism, its difference across principals for
the identical idempotency key, and that its separator can't be defeated by
a concatenation collision; that `record_response()` strips every
`REPLAY_HEADER_DENYLIST` entry (case-insensitively) while leaving other
headers untouched; and `InMemoryIdempotencyStore`'s idle-TTL eviction and
`max_keys` cap. `tests/test_fastapi.py` and `tests/test_django.py` exercise
the real middleware end to end: no-header pass-through, replay without
re-running the handler, 409 on a fingerprint conflict without reaching the
handler, 400 on an invalid key, per-key isolation, a `5xx` response NOT
being cached (a retry after a simulated failure actually re-runs and can
succeed), no key value ever appearing in a failure response body, conflict
logging by exception type only, **the same Idempotency-Key from two
different principals both executing (no cross-principal replay)**, **a
principal's own replay still working despite a different principal using
the identical key**, **an anonymous request (no principal) getting full
passthrough rather than a shared namespace**, **`principal_getter` being
required (FastAPI: `TypeError` if omitted; Django: `ImproperlyConfigured`
if neither passed nor configured via settings)**, and **a `Set-Cookie` on
the first response never appearing on a replay**.

Run:
```
uv run --python 3.13 --with fastapi --with httpx --with pytest --with 'django==5.2.*' -- \
  pytest templates/components/security/idempotency/tests/ -q
```

## Judgment calls

- **`BaseHTTPMiddleware`, not pure-ASGI.** Every sibling component in this
  directory (security-headers, cors-lockdown, rate-limiting) either avoids
  buffering entirely (pure-ASGI) or only needs to inspect headers. This
  component must capture a complete response body to replay later — there
  is no cheaper way to do that in Starlette than letting
  `BaseHTTPMiddleware` buffer it, so the usual "avoid `BaseHTTPMiddleware`"
  default from the other components does not apply here and is not a
  regression.
- **`5xx` responses are never cached.** The alternative (cache
  everything, including a transient 500) would mean a legitimate retry
  after a timeout gets permanently stuck replaying that same failure —
  strictly worse than the double-charge risk this component exists to
  prevent. `2xx`-`4xx` are treated as deterministic and cached; `5xx` is
  treated as transient and always re-attempted.
- **No reservation across the request lifecycle in
  `InMemoryIdempotencyStore`.** A record is written only after the
  downstream handler completes, so two truly concurrent requests with the
  identical key on the SAME process can both observe "unseen" and both
  execute the side effect once each before either result is recorded —
  documented as a known limitation (matching `InMemoryBucketStore`'s
  per-process disclosure in rate-limiting) rather than solved with a more
  complex in-process locking scheme that still wouldn't help across
  multiple workers/replicas anyway. A Redis-backed store (Stage 11) closes
  this with `SET NX` atomic reservation; that is the API shape
  `RedisIdempotencyStore`'s stub pins today.
- **`RedisIdempotencyStore` ships as a raising stub, not left undeclared.**
  Unlike rate-limiting (which mentions a future Redis `BucketStore` only in
  a docstring, with no class in code), this component includes an actual
  stub class satisfying the `IdempotencyStore` Protocol's shape that fails
  loudly (`NotImplementedError`) if constructed. The idempotency Protocol
  has a subtler two-field record (fingerprint + response) than the
  rate-limiter's numeric bucket state, so pinning its exact shape in code
  now — even unimplemented — is worth the small extra surface; a project
  that tries to reach for it before Stage 11 gets a clear, actionable error
  instead of discovering the class doesn't exist at all.
- **The key charset is intentionally narrower than "anything a client
  sends."** Idempotency keys aren't secret and aren't logged for their
  value, but they ARE used directly as a storage lookup key (and, in a
  Redis-backed store, as part of a cache key) — bounding length and
  restricting to `[A-Za-z0-9_.-]` is the same conservative posture
  cors-lockdown and rate-limiting take toward any value that becomes part
  of infrastructure-level state, applied here to a value the client fully
  controls.
- **`principal_getter` is required, with no default, in both adapters.** A
  default of "no principal scoping" would be the unsafe choice made
  silently — exactly the shape of bug this fix exists to close. Requiring
  it (a hard `TypeError`/missing-argument in FastAPI; a hard
  `ImproperlyConfigured` in Django when neither a kwarg nor a settings path
  is supplied) forces a deployer to make an explicit, deliberate choice
  about what identifies a "principal" in their app, rather than inheriting
  a default that happens to be wrong for a payments-adjacent feature.
- **The anonymous-request policy is "deny" (passthrough), not "hash the
  client IP automatically."** An automatic IP-based fallback would still be
  safer than the pre-fix behavior, but baking it in as the DEFAULT means a
  deployer never has to think about whether IP-based scoping is actually
  appropriate for their traffic (e.g. many users behind one NAT/corporate
  proxy sharing an IP would then collide with each other under an
  automatic fallback). Making the deployer write that fallback explicitly
  in their own `principal_getter`, if they want it, keeps the default
  behavior (full passthrough, identical to "no Idempotency-Key header")
  safe and boring, and puts the more nuanced per-IP tradeoff in the hands
  of whoever actually understands their own traffic shape.
- **`compute_storage_key` hashes rather than concatenates.** A plain
  `f"{principal}:{key}"` concatenation risks a boundary collision (`"a" +
  ":" + "b:c"` vs. `"a:b" + ":" + "c"`) unless the separator is proven
  never to appear in either input; hashing with a NUL separator (which
  cannot appear in a charset-validated `idempotency_key`, and is
  vanishingly unlikely in an application-controlled `principal`) sidesteps
  needing that proof, and additionally keeps the storage key a fixed,
  bounded length regardless of principal/key length.
- **`InMemoryIdempotencyStore`'s TTL default (24h) mirrors real-world
  idempotency-key retention conventions** (Stripe's own documented
  retention window is comparable) rather than an arbitrary shorter value —
  long enough that a legitimate delayed retry (a client's exponential
  backoff after a real outage) still hits the same stored record, short
  enough that the store doesn't grow forever under sustained traffic with
  no `max_keys` cap set.
