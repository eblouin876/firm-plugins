<!-- fragment: block:components/security/webhook-signature -->

## Setup
Copy the `webhook-signature/` directory into
`app/core/security/webhook_signature/`. FastAPI: `Depends(
make_webhook_verification_dependency(lambda: get_secret("STRIPE_WEBHOOK_SECRET")))`
on the webhook route, taking the verified raw bytes as the route's own
`bytes` parameter and `json.loads`-ing them itself. Django:
`@require_webhook_signature(lambda: get_secret("STRIPE_WEBHOOK_SECRET"))`
on the webhook view. Return a 2xx immediately and do the actual processing
asynchronously — a slow webhook handler causes provider-side retries (see
`references/security/payments-security.md`).

## Maintenance
Rotating a provider's signing secret: update the secret via
`secrets-loading`, no code change needed (`secret_getter` resolves fresh
per request). During a Stripe secret rotation specifically, Stripe sends
multiple `v1=` entries in the header for the overlap window — no config
change needed here either, `parse_stripe_style_header` already checks every
candidate. An empty/blank secret (e.g. an unset env var) now fails CLOSED
with `WebhookVerificationError` rather than silently accepting every
webhook — if verification starts failing for every request after a secret
rotation, check that `secret_getter()` is actually resolving a non-blank
value first.
