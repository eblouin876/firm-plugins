<!--
block: components/security/idempotency  # catalog component
last-verified: 2026-07-22
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
needs:
  - starlette/fastapi (via the project's FastAPI install): the middleware in fastapi.py
  - django (5.2.x): the middleware in django.py
  - a shared store for multi-process/multi-replica deployments (optional, Stage 11): InMemoryIdempotencyStore is per-process only, and does not reserve across the request lifecycle -- see Judgment calls
exposes:
  - IdempotencyStore (Protocol), InMemoryIdempotencyStore, RedisIdempotencyStore (Stage 11 stub, never imports redis), IdempotencyRecord, StoredResponse, IdempotencyOutcome, validate_key(raw_key), compute_fingerprint(method, path, raw_body), check(store, key, fingerprint), record_response(store, key, fingerprint, response, *, now=None) -- in _core.py
  - InvalidIdempotencyKeyError, IdempotencyConflictError
  - fastapi.py: IdempotencyMiddleware, add_idempotency(app, *, store, header_name="Idempotency-Key")
  - django.py: IdempotencyMiddleware (settings-configurable: IDEMPOTENCY_HEADER_NAME)
  - its co-located doc fragment: docs/fragment.md
-->

# idempotency

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: `Idempotency-Key` extraction/
validation and a method+path+body-hash fingerprint in `_core.py`, a
buffering `BaseHTTPMiddleware` in `fastapi.py`, and a Django `MIDDLEWARE`
class in `django.py` — both replaying a first-seen response verbatim for a
genuine retry, and returning `409` for the same key reused on a different
request. Embodies `references/security/payments-security.md`'s
"Idempotency keys" section: a retried request (network blip, client
double-submit) must never double-charge. Lives at
`templates/components/security/idempotency/` in this repo; Stage 3-4
backend blocks copy the whole directory into
`app/core/security/idempotency/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- The key/fingerprint/replay model
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

**EXPOSES**
- `IdempotencyStore` (Protocol), `InMemoryIdempotencyStore`,
  `RedisIdempotencyStore` (a Stage 11 stub that raises `NotImplementedError`
  on construction and never imports `redis`), `IdempotencyRecord`,
  `StoredResponse`, `IdempotencyOutcome`, `validate_key(raw_key)`,
  `compute_fingerprint(method, path, raw_body)`,
  `check(store, key, fingerprint)`, `record_response(store, key,
  fingerprint, response, *, now=None)` — all in `_core.py`.
- `InvalidIdempotencyKeyError`, `IdempotencyConflictError` — both subclass
  `IdempotencyError`.
- `fastapi.py`: `IdempotencyMiddleware`, `add_idempotency(app, *, store,
  header_name="Idempotency-Key")` (one-line wiring).
- `django.py`: `IdempotencyMiddleware` (settings-configurable:
  `IDEMPOTENCY_HEADER_NAME`, default `"HTTP_IDEMPOTENCY_KEY"`).
- Its co-located doc fragment: `docs/fragment.md`.

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
separate store instances not sharing state); and that `RedisIdempotencyStore`
raises `NotImplementedError` on construction with `redis` never imported.
`tests/test_fastapi.py` and `tests/test_django.py` exercise the real
middleware end to end: no-header pass-through, replay without re-running the
handler, 409 on a fingerprint conflict without reaching the handler, 400 on
an invalid key, per-key isolation, a `5xx` response NOT being cached (a
retry after a simulated failure actually re-runs and can succeed), no key
value ever appearing in a failure response body, and conflict logging by
exception type only.

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
