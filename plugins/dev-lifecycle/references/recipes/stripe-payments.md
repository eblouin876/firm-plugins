<!--
recipe: stripe-payments
applies-to:
  - backend block: django (references/backend/stripe.md's own reference stack — DRF + Celery) OR fastapi (same PCI/idempotency/audit posture; swap Celery's `.delay()` for the block's own async-processing seam — no dedicated task-queue block ships yet, see step 6)
  - frontend block: any React web block — Stripe Elements/Checkout runs client-side; the backend never receives card data
last-verified: 2026-07-23
provenance: manual
sources:
  - https://docs.stripe.com/security
  - https://docs.stripe.com/webhooks
  - https://docs.stripe.com/api/idempotent_requests
  - references/security/payments-security.md
  - references/backend/stripe.md
-->

# Stripe payments

Wire Stripe payments to the kit's payments-security baseline: tokenized card collection, verified webhooks, idempotent mutations, exact decimal money, a full audit trail, and least-privilege key handling. This is the **security-critical** recipe in this batch — every wire-up step below exists to satisfy a specific requirement in `references/security/payments-security.md`, cited inline. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Payments-security baseline coverage (acceptance checklist)
- Doc fragment

## What this wires
Applying this recipe gives a feature working Stripe payments that stay in PCI **SAQ-A** (the lightest self-assessment tier) by construction: the backend never receives, stores, or transits raw card data; every webhook is signature-verified before anything is trusted; every payment-mutating call (to Stripe, and into the app's own API) is idempotent; every amount is an exact `Decimal`/`numeric` in minor units; every payment-affecting event is audited; and the API keys never leave server-side storage.

It **composes existing pieces** — it invents no new payment infrastructure:
- **`references/security/payments-security.md`** — the authoritative, framework-neutral posture doc this whole recipe wires to. Every numbered step below cites the specific section it satisfies.
- **`references/backend/stripe.md`** — the SDK-level how-to (keys, PaymentIntent flow, webhook code, error handling, testing) this recipe's steps compile into; written against the Django/DRF/Celery stack specifically (its own header scopes it that way) — the FastAPI equivalents in the steps below adapt its patterns to Starlette/`async def`.
- **`templates/components/security/webhook-signature/`** — the dual-framework HMAC-SHA256 webhook verification component (`_core.py` + `fastapi.py`/`django.py`), built with Stripe's own `t=...,v1=...` header format as its reference shape. This is the webhook-signature-verification requirement, already built — this recipe wires it, it does not reimplement it.
- **`templates/components/security/idempotency/`** — the dual-framework `Idempotency-Key` middleware (principal-scoped storage key, replay-on-retry, `409` on a reused key with a different body). This is the app's-own-API half of the idempotency requirement — the Stripe-API half (an `idempotency_key` passed to `stripe.PaymentIntent.create`) is a plain SDK argument, not a separate component.
- **`templates/components/security/audit-logging/`** (see the `audit-logging` recipe) — `audit_event(...)` is the mechanism every payment-affecting event's audit trail is built on; `references/security/payments-security.md`'s "Full audit trail" section is explicitly "a specialization of the audit-logging control."
- **`templates/components/security/secrets-loading/secret_store.py`** — where `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` resolve from (env first, AWS Secrets Manager fallback) — the same mechanism every other secret in the app uses, never a bespoke Stripe-specific loader.

## Prerequisites
- A backend block (FastAPI or Django) with `secret_store.py`/`secrets-loading` vendored (ships by default in every backend block).
- The **`webhook-signature`** and **`idempotency`** catalog components vendored into the backend block (`app/core/security/webhook_signature/`, `app/core/security/idempotency/`) — neither is Stripe-specific, but this recipe is the first to require both together.
- The **`audit-logging`** component vendored (ships by default) — see the `audit-logging` recipe for its own wire-up detail; this recipe only adds the payment-specific call sites.
- An authentication layer already wired (`end-to-end-auth` recipe or equivalent) — the idempotency component's `principal_getter` requires a resolved caller identity, and a checkout endpoint should not be anonymous in the common case.
- `stripe-python` — pinned in `references/backend/stripe.md`'s own "Version check" section (`stripe-python 15.3.0` / API `2026-06-24.dahlia`) rather than `references/compatibility-matrix.md`, which does not yet carry a Stripe row — pin against that doc's version-check guidance, and re-verify against PyPI/Stripe's migration notes before bumping either axis.
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` obtained from the Stripe Dashboard (test-mode keys for dev/CI; live keys only in prod's Secrets Manager) — see `references/security/secrets-management.md`'s per-secret table, which already carries both rows.

## Wire-up steps

1. **Collect card data client-side only — Stripe Elements or Checkout.** *(Satisfies payments-security.md's "Tokenization: never store card data.")* The frontend block integrates Stripe.js/Elements (or redirects to a Checkout Session); a raw PAN never reaches the app's backend, request logs, or database. The backend's only job in this flow is creating a PaymentIntent/Checkout Session server-side and returning its `client_secret`/URL — never accepting card fields in a request body. Only the **publishable key** (`pk_...`) reaches the browser; it is not secret and can be a build-time public env var. The **secret key** (`sk_...`) is never sent to the client under any name — critically, **never as `NEXT_PUBLIC_*` (Next.js) or `VITE_*` (Vite)**, both of which get inlined into the client bundle at build time. Store only Stripe's own identifiers (`customer`, `payment_intent`, `charge`, `subscription`, `payment_method` IDs) on the app's own models — safe to persist, not card data.

2. **Resolve `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` via `secret_store.get_secret(...)`, never inline or in `NEXT_PUBLIC_*`/`VITE_*`.** *(Satisfies "least-privilege API-key handling" and `secrets-management.md`'s pattern.)* Both resolve env-first with an AWS Secrets Manager fallback — the same mechanism `JWT_SIGNING_KEY`/`SMTP_*` already use in this kit, not a Stripe-specific loader. Separate test (`sk_test_`/`pk_test_`) and live keys, selected by environment, never hardcoded. Never log a key, and never log a full Stripe request/response that could carry one — see `stripe.md`'s "Keys and secrets" section. Set `stripe.api_version` explicitly (pinned in `stripe.md`'s "Version check" section) so an SDK bump can't silently move the API version underneath the integration.

3. **Verify every webhook's signature with the `webhook-signature` component before trusting the payload.** *(Satisfies "Webhook signature verification.")* Wire the Stripe endpoint through the component rather than hand-rolling `stripe.Webhook.construct_event` call sites: FastAPI — `Depends(make_webhook_verification_dependency(lambda: get_secret("STRIPE_WEBHOOK_SECRET")))` on the route, taking the dependency's returned verified raw bytes and `json.loads`-ing them for the event payload; Django — `@require_webhook_signature(lambda: get_secret("STRIPE_WEBHOOK_SECRET"))` on the webhook view. Both adapters read the **raw** body ahead of any parsing (a parsed/re-serialized body won't match the signature) and reject with a generic `400` on any verification failure — never distinguishing which check failed in the response. The client confirming payment is never proof of payment; only a verified webhook (or a server-initiated `retrieve`) is.

4. **Dedupe incoming webhook events by Stripe's `event.id`.** *(Satisfies "Idempotency keys" — the consuming side.)* Webhook delivery is at-least-once and unordered: persist `event.id` with a unique constraint (or `get_or_create`/upsert) so a redelivered event applies its effect exactly once, and re-fetch the current object state from the event payload rather than assuming events arrive in order.

5. **Pass a stable `idempotency_key` on every Stripe-mutating call.** *(Satisfies "Idempotency keys" — the producing side.)* `stripe.PaymentIntent.create(..., idempotency_key=f"pi-create-{order_id}")` — derived from a stable operation identifier, never random per attempt — so a retried request (network blip, client double-submit) can never double-charge. This is a plain SDK argument; there is no separate component for it.

6. **Protect the app's own payment-initiating endpoint(s) with the `idempotency` component, wired AFTER auth.** *(Satisfies "Idempotency keys" — the app's-own-API half, and is the concrete reason this recipe requires the `idempotency` component as a prerequisite, not payments-specific by itself.)* FastAPI: `add_idempotency(app, store=InMemoryIdempotencyStore(), principal_getter=lambda request: request.state.user_id)`, registered so it executes after auth on the request path (see the component's own "Principal scoping" section for the registration-order subtlety). Django: add its `IdempotencyMiddleware` to `MIDDLEWARE` after `AuthenticationMiddleware`. A client that retries a `POST /checkout` (e.g. a double-tapped button) replays the first response instead of creating a second PaymentIntent.

7. **Return `2xx` from the webhook handler immediately; keep the actual processing fast and idempotent rather than deferring it into infrastructure this kit doesn't ship yet.** *(Satisfies "Webhook signature verification"'s delivery-latency requirement.)* `stripe.md`'s own reference implementation hands the verified event to Celery (`process_stripe_event.delay(event.id, event.type)`) and acknowledges within milliseconds — do this on the Django track if Celery is already wired in the project. On FastAPI, or on a Django project without Celery yet, do the minimal idempotent DB write (the `event.id` dedup from step 4, plus the resulting state change) **inline**, synchronously, before returning `200` — a few DB writes is normally fast enough to avoid Stripe's retry window on its own. A background job queue for heavier post-processing (fulfillment side effects, notification fan-out) is explicitly out of scope here — that is the kit's separate, later "background jobs" recipe; don't invent a queue inline in this one.

8. **Represent every amount as `Decimal`/the ORM's native `numeric` column, in the currency's minor unit — never `float`.** *(Satisfies "Decimal money types, never float" and "Amounts in minor units.")* `$9.99` is stored and sent as the integer `999`, not `9.99`; round to the minor unit once, at the boundary, on the way to Stripe — never repeatedly through intermediate calculations. Store `currency` explicitly alongside every amount (note JPY and similar currencies have no minor unit — don't assume `÷100` universally). **The server decides the amount and currency for a charge, always** — never accept an amount or currency from the client request body; derive it from the order/cart the server itself already knows.

9. **Wire `audit_event(...)` at every payment-affecting state change.** *(Satisfies "Full audit trail," an explicit specialization of the `audit-logging` component's control — see the `audit-logging` recipe for the component's own wire-up detail.)* At minimum: intent created, succeeded, failed, refunded, disputed, and subscription changed. Follow the same shape as the kit's own `admin.user.*` worked example: `audit_event("payment.intent.succeeded", actor=f"user:{user_id}", resource=f"payment_intent:{event.data.object.id}", outcome="success", amount_minor=event.data.object.amount, currency=event.data.object.currency)` — `actor`/`resource` are identifiers, `amount_minor`/`currency` are safe non-PII facts about the transaction (never card data — none is ever available to audit in the first place, by construction of step 1). This is the record that answers "what did the customer see, what did Stripe say, did our system's state match" for any transaction, after the fact.

10. **Reconcile periodically against Stripe's own record.** *(Satisfies "Reconciliation.")* Compare the app's payment/order records against the Dashboard, the API, or a Sigma export on a schedule — webhook delivery gaps, retried events, and manual Dashboard actions can all cause silent drift if the app is the only source of truth. Treat a mismatch as a bug to root-cause, never a value to silently overwrite.

## Payments-security baseline coverage (acceptance checklist)
Every `references/security/payments-security.md` requirement this recipe satisfies, and where:
- [ ] **Tokenization / no card data stored or transiting the server** — step 1 (Stripe Elements/Checkout; only Stripe IDs persisted).
- [ ] **Webhook signature verification** — step 3 (`webhook-signature` component, raw body, constant-time compare, generic `400`).
- [ ] **Idempotency keys** — steps 4–6 (webhook `event.id` dedup, `idempotency_key` on every Stripe mutation, the `idempotency` component on the app's own checkout endpoint).
- [ ] **Decimal money, never float** — step 8 (`Decimal`/`numeric`, minor units, explicit `currency`, server-decided amount).
- [ ] **Full audit trail** — step 9 (`audit_event(...)` at every payment-affecting state change).
- [ ] **Least-privilege API-key handling** — step 2 (`secret_store`/Secrets Manager; secret key never `NEXT_PUBLIC_*`/`VITE_*`; test vs. live key separation).
- [ ] **Reconciliation** — step 10.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Payments (Stripe)
- **Setup:** Card collection is client-side only (Stripe Elements/Checkout) — the backend creates PaymentIntents/Checkout Sessions and never receives card data. The webhook endpoint verifies every event via the `webhook-signature` component before trusting it (raw body, `Stripe-Signature`), dedupes by `event.id`, and processes inline (or via Celery on the Django track) before returning `2xx`. The checkout endpoint is protected by the `idempotency` component (`Idempotency-Key`, principal-scoped) in addition to a stable `idempotency_key` passed on every Stripe-mutating call. All amounts are `Decimal`/`numeric`, stored in minor units with an explicit currency; the server always decides the charged amount. Every payment-affecting event is audited via `audit_event(...)`.
- **Secrets:** `STRIPE_SECRET_KEY` — Stripe Dashboard → Developers → API keys (test key for dev/CI, live key only in prod's Secrets Manager); never exposed to the client, never `NEXT_PUBLIC_*`/`VITE_*`. `STRIPE_WEBHOOK_SECRET` — Stripe Dashboard → Developers → Webhooks → select endpoint → Signing secret. Both resolve via `secret_store.get_secret(...)`.
- **Maintenance:** Reconcile app payment/order records against Stripe's Dashboard/API/Sigma export periodically — treat a mismatch as a bug, not a value to overwrite. Rotate `STRIPE_SECRET_KEY` on a calendar reminder (no automatic rotation) and whenever a team member with Dashboard access leaves. Re-verify the `stripe-python` SDK/API version pin (`references/backend/stripe.md`'s own version-check section) before bumping either axis — a named API version (`.dahlia`-style) is a breaking-change event, not a routine bump.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34). Composes the
existing webhook-signature, idempotency, audit-logging, and secrets-loading
catalog components plus references/security/payments-security.md and
references/backend/stripe.md — no new payment infrastructure invented. Every
payments-security.md requirement is traced to a specific step above; see
this file's own "Payments-security baseline coverage" section.
-->
