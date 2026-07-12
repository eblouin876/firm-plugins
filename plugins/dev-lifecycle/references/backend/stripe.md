<!--
library: stripe
versions-covered: "stripe-python 15.3.0 / API 2026-06-24.dahlia"
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://pypi.org/project/stripe/
  - https://github.com/stripe/stripe-python/releases
  - https://raw.githubusercontent.com/stripe/stripe-python/master/README.md
  - https://docs.stripe.com/sdks/versioning
  - https://docs.stripe.com/webhooks
  - https://docs.stripe.com/error-handling?lang=python
-->

# Stripe conventions

Idioms for correct, secure payments via the `stripe` Python SDK in this Django/DRF/Celery app. Load when `stripe` is in requirements. Subordinate to project conventions — where the codebase already picks a pattern, match it.

## Contents
- Version check (do this first)
- Keys and secrets
- Money handling
- Payment flow (PaymentIntents / Checkout)
- Webhooks are the source of truth
- Idempotency
- What you store (PCI)
- Customers and subscriptions
- Errors
- Testing

## Version check (do this first)
Two independent version axes — pin both, upgrade each deliberately.
- **SDK version:** `pip show stripe` → currently 15.3.0 (Python >=3.9). Bumping the SDK can change method surfaces (e.g. the newer `StripeClient` vs global `stripe.api_key`).
- **Stripe API version:** date-stamped, pinned per account (Dashboard) and overridable per request. SDK 15.3.0 ships default `2026-06-24.dahlia`. Monthly releases are backward-compatible; the named major (`.dahlia`) is a **breaking-change event** — request shapes, webhook payloads, and object fields change. Upgrade against Stripe's migration guide, in test mode, never as a drive-by. Pin explicitly so an SDK bump can't silently move the API version:

```python
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = "2026-06-24.dahlia"   # or client.v1.customers.list(options={"stripe_version": ...})
```

## Keys and secrets
- Secret key (`sk_...`) **server-side only**; publishable key (`pk_...`) is the only key that reaches the browser.
- Separate test (`sk_test_`/`pk_test_`) and live keys; select by environment, never hardcode.
- Load from env/secret store — never commit, never log a key or a full request/response containing one. See `owasp.md` for secret handling.

## Money handling
- Amounts are **integers in the smallest currency unit** (cents, pence; yen has no minor unit). `$9.99` → `999`.
- **Never floats for money** — use `int`/`Decimal` in your domain, pass ints to Stripe. Round to minor units at the boundary, once.
- Always pass `currency` explicitly; store it alongside every amount.

## Payment flow (PaymentIntents / Checkout)
Use PaymentIntents or Checkout Sessions — **not** the legacy Charges API. Server creates the intent; client confirms with Stripe.js/Elements using the `client_secret`.

```python
intent = stripe.PaymentIntent.create(
    amount=999, currency="usd",
    customer=customer_id,
    metadata={"order_id": order.pk},
    idempotency_key=f"pi-create-{order.pk}",
)
# return intent.client_secret to the client; it confirms card-side.
```
Anti-pattern: creating a Charge, or taking `amount`/`currency` from the client request body — the server decides the amount.

## Webhooks are the source of truth
Do not mark an order paid because the browser said so. Confirm via the webhook (or a server-side `retrieve`).

```python
@csrf_exempt
def stripe_webhook(request):
    try:
        event = stripe.Webhook.construct_event(
            request.body,                              # raw bytes, not parsed JSON
            request.META["HTTP_STRIPE_SIGNATURE"],
            settings.STRIPE_WEBHOOK_SECRET,            # whsec_..., per endpoint
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)
    process_stripe_event.delay(event.id, event.type)   # Celery; ack fast
    return HttpResponse(status=200)
```
- Verify signatures with `construct_event` (default tolerance 300s); reject on failure. Never trust an unverified payload.
- **Return 2xx immediately, process async.** Hand the event to Celery and reconcile there — see `celery.md`. Slow handlers cause Stripe retries.
- Delivery is **at-least-once and unordered** → handlers must be idempotent (below) and re-fetch objects rather than assume ordering.
- Handle the events you rely on: `payment_intent.succeeded`, `payment_intent.payment_failed`, `checkout.session.completed`, `invoice.paid`, etc.

## Idempotency
- Pass `idempotency_key` on every create/mutation so a retried request never double-charges (the SDK auto-generates one per retry, but supply your own stable key derived from the operation for cross-request safety).
- On the consuming side, dedupe by Stripe `event.id` (unique constraint / `get_or_create`) so redelivered webhooks apply once.

## What you store (PCI)
- Store Stripe IDs — `customer`, `payment_intent`, `charge`, `subscription` — never raw card data. Card data never touches your server: collect it with Elements/Checkout.
- Touching a raw PAN pulls you into PCI scope. Don't.

## Customers and subscriptions
- Create a `stripe.Customer` once per user; persist `cus_...` on your model, reuse it. Subscriptions/invoices hang off the customer.
- Drive subscription state from webhooks (`customer.subscription.updated/deleted`, `invoice.paid`), not from the create call's return.

## Errors
Catch typed exceptions (top of `stripe.py`; legacy alias `stripe.error.*`). Distinguish **card errors** (user-actionable, expected) from **API errors** (bugs/outages).

```python
try:
    intent = stripe.PaymentIntent.create(...)
except stripe.CardError as e:
    return Response({"error": e.user_message}, status=402)   # declined, etc.
except stripe.RateLimitError:
    ...  # back off / retry
except stripe.StripeError:
    logger.exception("stripe api error")                     # never log keys/PAN
    return Response({"error": "payment failed"}, status=502)
```

## Testing
- Test mode only in CI; test cards (`4242 4242 4242 4242`, `4000 0000 0000 0002` decline) — never real cards.
- Forward events locally with the Stripe CLI: `stripe listen --forward-to localhost:8000/webhooks/stripe/`.
- In unit tests, mock `stripe.*` calls and feed `construct_event` fixture payloads — don't hit the network.
