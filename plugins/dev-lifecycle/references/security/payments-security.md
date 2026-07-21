<!--
library: payments-security
versions-covered: "PCI DSS v4.0.1, Stripe API (see backend/stripe.md for the pinned SDK/API version)"
last-verified: 2026-07-21
provenance: manual
sources:
  - https://docs.stripe.com/security
  - https://docs.stripe.com/webhooks
  - https://docs.stripe.com/api/idempotent_requests
  - https://www.pcisecuritystandards.org/document_library/
-->

# Payments security

PCI-conscious money handling, with Stripe as the reference implementation (canon for the Stage 11 Stripe recipe). The goal of every pattern here is the same: **stay in SAQ-A** (the lightest PCI self-assessment tier) by never letting raw card data touch the app's servers.

## Contents
- Version check (do this first)
- Tokenization: never store card data
- Webhook signature verification
- Idempotency keys
- Decimal money types, never float
- Amounts in minor units
- Full audit trail
- Reconciliation

## Version check (do this first)
PCI DSS v4.0.1 is current. Stripe's SDK/API version pin is tracked in `references/backend/stripe.md` — check there before writing Stripe-integration code; this doc covers the money-handling and PCI posture that applies regardless of SDK version.

## Tokenization: never store card data
- Collect card details client-side only, via Stripe Elements/Checkout — a raw PAN (card number) never reaches the app's backend, request logs, or database. This is what keeps the integration in **SAQ-A**; touching a raw PAN pulls the whole app into a much heavier PCI scope.
- Store only Stripe's own identifiers (`customer`, `payment_intent`, `charge`, `subscription`, `payment_method` IDs) — these are safe to persist and reference; they are not card data.
- Never log a full request/response that could contain card data or a secret API key, even accidentally via a debug logger.

## Webhook signature verification
- The client confirming a payment is not proof of payment — **verify server-side via the webhook**, or a server-initiated `retrieve`, before marking anything paid or fulfilled.
- Verify every webhook's signature (`Stripe-Signature` header against the endpoint's signing secret) before trusting the payload; reject on verification failure. Read the **raw request body** for verification — a parsed/re-serialized body will not match the signature.
- Webhook delivery is at-least-once and unordered: handlers must be idempotent (below) and re-fetch the current object state rather than assume the payload reflects the latest state or that events arrive in order.
- Return a 2xx immediately and do the actual processing asynchronously (task queue) — a slow handler causes retries and can cascade into duplicate processing.

## Idempotency keys
- Pass an idempotency key on every payment-mutating request (create a PaymentIntent, capture, refund) derived from a stable operation identifier (e.g. `f"pi-create-{order_id}"`) — a retried request (network blip, client double-submit) must never double-charge.
- On the consuming side, dedupe incoming webhook events by their event ID (unique constraint / upsert) so a redelivered event applies its effect exactly once.

## Decimal money types, never float
- Represent money with an exact type — `Decimal` (Python) or the ORM/DB's native `numeric`/`decimal` column — never `float`/`double`. Floats introduce rounding error that compounds across a ledger and will eventually misstate a balance.
- Round to the currency's minor unit at the boundary, once, on the way to the payment provider — don't round repeatedly through intermediate calculations.

## Amounts in minor units
- Send and store amounts as **integers in the smallest currency unit** (cents for USD, pence for GBP; note some currencies, like JPY, have no minor unit — check before assuming ÷100). `$9.99` is `999`, not `9.99`.
- Always store and pass `currency` explicitly alongside every amount — an amount without a currency is not a complete fact.
- The server decides the amount and currency for a charge, always — never trust an amount/currency sent from the client request body.

## Full audit trail
- Every payment-affecting event (intent created, succeeded, failed, refunded, disputed, subscription changed) is persisted with its Stripe event ID, timestamp, and the resulting state change — this is the record that reconciliation and support both depend on.
- This is a specialization of the audit-logging control in `references/security/secure-baseline.md`: for payments specifically, the audit trail must be sufficient to answer "what did the customer see, what did Stripe say, and did our system's state match" for any transaction, after the fact.

## Reconciliation
- Periodically reconcile the app's payment/order records against Stripe's own record (via the Dashboard, the API, or Stripe's reporting/Sigma exports) — webhook delivery gaps, retried events, and manual Dashboard actions can all cause silent drift if the app is the only source of truth.
- Treat a reconciliation mismatch as a bug to root-cause (missed webhook, race condition, a manual refund the app didn't observe), not a value to overwrite silently.

## Related canon
`references/security/secure-baseline.md` is the general bar this doc specializes for payments; `references/security/secrets-management.md` covers where the Stripe API keys and webhook signing secret live; `references/backend/stripe.md` is the SDK-level how-to (keys, flow, error handling, testing) this doc's principles compile into.
