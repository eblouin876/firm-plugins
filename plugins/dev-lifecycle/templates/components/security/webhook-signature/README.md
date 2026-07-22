<!--
block: components/security/webhook-signature  # catalog component
last-verified: 2026-07-22
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
needs:
  - starlette/fastapi (via the project's FastAPI install): the dependency in fastapi.py, which reads the RAW body ahead of any parsing
  - django (5.2.x): the view decorator in django.py, which reads request.body directly
  - a webhook signing secret per provider (e.g. via secrets-loading's get_secret()): this component verifies against a secret the caller resolves and passes in, it does not fetch one itself
exposes:
  - verify(raw_body, signature_header, secret, *, tolerance_s=300, now=None) -> None (raises WebhookVerificationError subtypes on failure), compute_signature(secret, timestamp, raw_body) -> str, parse_stripe_style_header(header) -> ParsedSignatureHeader -- in _core.py
  - WebhookVerificationError, MissingSignatureHeaderError, MalformedSignatureHeaderError, TimestampToleranceError, SignatureMismatchError
  - fastapi.py: make_webhook_verification_dependency(secret_getter, *, header_name="stripe-signature", tolerance_s=300)
  - django.py: require_webhook_signature(secret_getter, *, header_name="HTTP_STRIPE_SIGNATURE", tolerance_s=300)
  - its co-located doc fragment: docs/fragment.md
-->

# webhook-signature

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: HMAC-SHA256 verification over the
RAW body with a replay-window timestamp tolerance and constant-time
comparison in `_core.py`, a FastAPI dependency in `fastapi.py`, and a Django
view decorator in `django.py`. Embodies
`references/security/payments-security.md`'s "Webhook signature
verification" section exactly — the reference header format is Stripe's
`t=...,v1=...`, generic enough to adapt to another provider's HMAC-SHA256
scheme. Lives at `templates/components/security/webhook-signature/` in this
repo; Stage 3-4 backend blocks copy the whole directory into
`app/core/security/webhook_signature/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- Why the RAW body, always
- The Stripe-style reference format
- The replay window
- Constant-time comparison
- Never logs a signature or secret value
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Starlette/FastAPI** (via the project's FastAPI install) — the
  dependency in `fastapi.py` reads the raw body via `await request.body()`
  before any JSON-parsing dependency runs.
- **Django 5.2.x** — the view decorator in `django.py` reads
  `request.body` directly, before the view touches `request.POST`/`.data`.
- **A webhook signing secret per provider** — this component verifies
  against a secret the caller resolves and passes in (typically via
  `secrets-loading`'s `get_secret("STRIPE_WEBHOOK_SECRET")`); it does not
  fetch, cache, or know about secret storage itself.

**EXPOSES**
- `verify(raw_body, signature_header, secret, *, tolerance_s=300, now=None)
  -> None` (raises a `WebhookVerificationError` subtype on failure, returns
  nothing on success), `compute_signature(secret, timestamp, raw_body) ->
  str`, `parse_stripe_style_header(header) -> ParsedSignatureHeader` — all
  in `_core.py`.
- `WebhookVerificationError` (base) and its subtypes
  `MissingSignatureHeaderError`, `MalformedSignatureHeaderError`,
  `TimestampToleranceError`, `SignatureMismatchError` — distinct types for
  logging/debugging; both adapters collapse all of them to the same generic
  400 response (see "Judgment calls").
- `fastapi.py`: `make_webhook_verification_dependency(secret_getter, *,
  header_name="stripe-signature", tolerance_s=300)`.
- `django.py`: `require_webhook_signature(secret_getter, *,
  header_name="HTTP_STRIPE_SIGNATURE", tolerance_s=300)`.
- Its co-located doc fragment: `docs/fragment.md`.

## Why the RAW body, always

Per `references/security/payments-security.md`: "Read the raw request body
for verification — a parsed/re-serialized body will not match the
signature." Both adapters read the body before any parsing touches it: the
FastAPI dependency calls `await request.body()` directly (Starlette caches
the raw bytes internally, so a route handler or another dependency reading
the body afterward sees the same cached bytes, not a second read of an
already-consumed stream); the Django decorator reads `request.body`
directly, ahead of the wrapped view ever calling `request.POST` or a DRF
`request.data`.

## The Stripe-style reference format

`t=<unix timestamp>,v1=<hex hmac>[,v1=<hex hmac>...]` — Stripe's own format,
used as the reference because it's well-documented and handles secret
rotation cleanly (multiple `v1=` entries, one per active signing secret; a
single match against any of them is sufficient — see
`parse_stripe_style_header`). An older `v0=` scheme Stripe still sends
alongside is parsed but ignored, matching Stripe's own documented posture of
verifying `v1` only. A different provider's HMAC-SHA256 webhook scheme
(different header name, different signed-payload construction) adapts by
writing a provider-specific parser that produces the same
`ParsedSignatureHeader` shape and calling `verify()`'s constituent pieces
(`compute_signature`, the constant-time compare) directly, rather than
`parse_stripe_style_header` itself, which is Stripe-shaped by name and by
contract.

## The replay window

`tolerance_s` (default 300s / 5 minutes) bounds how far the signed
timestamp may drift from `now` in **either** direction — a timestamp
claiming to be from the future fails exactly like a stale one, since both
are equally a sign the value isn't a fresh, genuine delivery. This is the
mechanism that turns "an attacker replays a captured, validly-signed
request days later" from a valid request into a rejected one: the HMAC
alone proves the payload+timestamp pair was signed by the secret holder at
some point, not that it was signed *now*.

## Constant-time comparison

Every candidate signature is checked via `hmac.compare_digest`, never `==`
or any other short-circuiting string comparison — a naive `==` comparison
exits as soon as it finds the first mismatched byte, and the tiny timing
difference between "failed at byte 3" and "failed at byte 30" is a real,
exploitable side channel (a byte-at-a-time timing attack) an attacker with
enough requests can use to forge a valid signature without knowing the
secret. `hmac.compare_digest` runs in time that depends only on the length
of the inputs, not their content.

## Never logs a signature or secret value

`_core.py` itself never logs anything (verified in
`tests/test_core.py::test_verify_itself_never_logs_anything`) — logging is
each framework adapter's responsibility, and both log a failure by
**exception type name only** (`SignatureMismatchError`,
`TimestampToleranceError`, ...), never the header string, the computed
digest, or the secret. Every `WebhookVerificationError` subtype's own
message also never carries a signature or secret value — see
`tests/test_core.py::test_exception_messages_never_contain_the_signature_or_secret`.

## Testing

`tests/test_core.py` covers valid verification (including multiple `v1=`
candidates for key rotation), tampered-body rejection, wrong-secret
rejection, expired AND future-timestamp rejection, every
`MalformedSignatureHeaderError`/`MissingSignatureHeaderError` trigger,
`parse_stripe_style_header`'s shape (including ignoring an unrelated `v0=`
scheme), that `hmac.compare_digest` is the actual comparison reached on
both the pass and fail path (via a monkeypatched spy wrapping the real
function), and that neither `_core.py`'s logging (there is none) nor any
exception message ever contains the signature or secret value.
`tests/test_fastapi.py` and `tests/test_django.py` exercise the same
valid/tampered/expired/missing-header cases end-to-end through a real
FastAPI `TestClient` / Django `RequestFactory`, plus that a failure never
reaches the view function body (Django: asserts the wrapped view's own call
list stays empty) and that neither the HTTP response body nor the adapter's
warning log line ever contains the header or secret.

Run:
```
uv run --python 3.13 --with fastapi --with httpx --with pytest --with 'django==5.2.*' -- \
  pytest templates/components/security/webhook-signature/tests/ -q
```

## Judgment calls

- **All four failure subtypes collapse to the same generic 400 in both
  adapters.** `verify()` itself raises distinguishable exception types
  (useful for logging/debugging, and for a caller writing its own custom
  adapter that wants to react differently), but the response a webhook
  sender actually receives never distinguishes "you sent no signature" from
  "your signature was wrong" from "your timestamp was stale" — leaking
  which check failed is a small information disclosure a legitimate
  integration never needs, and it very slightly narrows what an attacker
  probing the endpoint has to guess next.
- **`secret_getter` is a callable, not a secret string, in both adapters.**
  Resolving fresh per request (rather than capturing the secret once at
  dependency-construction/decorator-application time) means a project
  rotating its webhook signing secret via `secrets-loading`'s
  `get_secret()` — env var change, or an AWS Secrets Manager value update —
  takes effect on the next request with no redeploy needed to rebuild a
  captured closure.
- **`compute_signature`/`parse_stripe_style_header` are exposed standalone,
  not just used internally by `verify()`.** `compute_signature` doubles as
  the tool for building a valid signature in a test fixture (used
  throughout this component's own tests) or for signing an outbound webhook
  this app sends to another service with the same scheme; a project
  integrating a non-Stripe provider can still reuse the constant-time-
  compare and tolerance-window logic in `verify()` while writing its own
  parser, rather than reimplementing the whole file.
