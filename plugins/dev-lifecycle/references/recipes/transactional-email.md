<!--
recipe: transactional-email
applies-to:
  - backend block: fastapi (SmtpEmailSender) OR django (DjangoEmailSender) — same EmailSender Protocol, framework-specific delivery adapter
last-verified: 2026-07-23
provenance: manual
sources:
  - templates/components/security/auth/README.md
  - templates/components/security/auth/_core.py
  - references/security/secrets-management.md
-->

# Transactional email

Wire the existing `EmailSender` abstraction (shipped with the auth component) for verification/reset email and for arbitrary transactional email a feature needs to send (a receipt, a notification, an invite) — without inventing a second delivery seam. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- The fire-and-forget, non-raising contract (read this before touching a sender)
- Doc fragment

## What this wires
Applying this recipe gives a feature working transactional email delivery through the same seam auth's verify/reset flow already uses — one `EmailSender` Protocol, one production adapter per backend track, and the enumeration-safe, non-raising posture that makes it safe to call from a request path.

It **composes existing pieces** — it invents no new infrastructure:
- **`templates/components/security/auth/_core.py`** — `EmailMessage` (a plain-text dataclass: `to`, `subject`, `body` — no HTML templating engine, no injection surface) and the `EmailSender` Protocol (`async def send(self, message: EmailMessage) -> None`). `ConsoleEmailSender` is the one implementation this framework-neutral core ships — **dev/test only**, logs the message (including any token in the body) instead of delivering it.
- **`templates/backend/fastapi/app/core/security/auth/stores.py`**'s `SmtpEmailSender` — the FastAPI track's production adapter: stdlib `smtplib` + `email.message.EmailMessage`, no third-party email library. `get_email_sender(settings)` returns `ConsoleEmailSender()` when `settings.smtp_host` is unset, else a real `SmtpEmailSender` built from `settings.smtp_*`/`email_from`.
- **`templates/backend/django/core/security/auth/stores.py`**'s `DjangoEmailSender` — the Django track's production adapter, built on Django's own pluggable `django.core.mail` backend (`settings.EMAIL_BACKEND`) rather than a second hand-rolled SMTP client.
- **`templates/components/security/secrets-loading/secret_store.py`** — where `smtp_host`/`smtp_port`/`smtp_username`/`smtp_password`/`email_from` resolve from (process env first, AWS Secrets Manager fallback), same as every other secret in the app.

## Prerequisites
- A backend block with the auth component vendored (both tracks ship an `EmailSender` seam already, whether or not auth's verify/reset flow is in use — the Protocol and `ConsoleEmailSender` live in the framework-neutral core either way).
- `SMTP_HOST` (+ `SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM`) configured in every non-dev environment — a real relay for the FastAPI track's `SmtpEmailSender`, or a Django `EMAIL_BACKEND` pointed at one for the Django track. Unset falls open to `ConsoleEmailSender`/Django's console backend (dev-only; logs the raw message, including any token in the body).
- No new dependency: the FastAPI adapter is stdlib `smtplib` only; the Django adapter uses Django's own mail machinery — neither pins a new line on `references/compatibility-matrix.md`.

## Wire-up steps
1. **Reuse the existing `EmailSender` seam for any new transactional email — don't add a second one.** A feature that needs to send a receipt, an invite, or a notification builds an `EmailMessage(to=..., subject=..., body=...)` and calls the same injected `EmailSender.send(message)` `AccountService` already uses for verify/reset — construct it via the block's existing `get_email_sender(settings)` (FastAPI) or the Django track's equivalent factory, not a new client.

2. **Keep the body plain text.** `EmailMessage` is deliberately plain-text-only — no templating engine, no HTML-injection surface to worry about. Build the body as an f-string/plain template; do not extend `EmailMessage` with an HTML field without also adding the injection-review that decision implies (out of scope for this recipe — treat it as a deliberate follow-on decision, not a drive-by).

3. **Never let `send()` block or raise into the caller's request path.** Both adapters schedule delivery and return immediately: `SmtpEmailSender.send()` (FastAPI) does `asyncio.create_task(self._deliver(message))`; `DjangoEmailSender.send()` (Django) submits to a module-level `ThreadPoolExecutor` (`_email_executor`, `max_workers=4`). Neither awaits the network round-trip, and neither propagates a delivery failure — `_deliver`/`_deliver_sync` catches every exception and only logs a `warning`. A new call site that awaits `send()` and inspects its result for delivery success is wiring against the contract; there is no result to inspect.

4. **On the Django track specifically, never swap `ThreadPoolExecutor` for `asyncio.create_task`.** This is a fixed, hard-won bug in this kit: an earlier version of `DjangoEmailSender` used `asyncio.create_task`, the same pattern `SmtpEmailSender` correctly uses on FastAPI. It silently broke delivery — every DRF view reaches `AccountService` via `asgiref.sync.async_to_sync(...)`, which spins up a *fresh* event loop per call and tears it down before that call returns; a task merely *scheduled* (not yet run) on that loop is gone the instant `async_to_sync` returns, and the email is never sent. `ThreadPoolExecutor` sidesteps this because a submitted job starts on a real OS thread immediately, independent of whichever event loop (if any) is running when `send()` is called. If a new feature adds its own async-to-sync bridge point on the Django track, route email sends through `DjangoEmailSender`, not a fresh `asyncio.create_task` call.

5. **Verify the enumeration-safe posture end to end, not just that mail sends.** `AccountService.request_password_reset`'s known-email branch `await`s `send()` and then returns exactly the same response as the unknown-email branch — this only stays true because `send()` can neither raise nor block on the real SMTP/relay round-trip. A new call site built on this seam inherits the same property automatically; a call site that bypasses the seam (e.g. calls `smtplib` directly "just this once") does not, and can reintroduce a timing or error-shape oracle.

6. **Confirm the deploy-time requirement, not a code check.** A missing `SMTP_HOST`/`EMAIL_BACKEND` fails **open and quiet** by design (the app keeps serving, `ConsoleEmailSender`/the console backend silently takes over) — there is no code-level fail-closed guard, deliberately, because the "is this really prod?" check that guard would need is easy to get wrong. Confirm the real relay is configured as an operational deploy-checklist item in every non-dev environment, not something a passing test suite proves.

## The fire-and-forget, non-raising contract (read this before touching a sender)
`EmailSender.send()`'s Protocol docstring states the rule any new implementation or call site must hold: **implementations MUST NOT let delivery latency or delivery failure affect the caller.** Two things depend on it, not just speed:
- **Anti-enumeration**: a known-email vs. unknown-email password-reset request must return in the same shape and the same rough latency regardless of whether delivery actually succeeds.
- **Registration resilience**: a failed verification-email send during registration must never brick a just-created account.

`ConsoleEmailSender` satisfies this trivially (it only logs, synchronously, and cannot itself fail in a way worth propagating). Any real sender — the two shipped adapters, or a third one for a different provider — must actively deliver **out of band** (a background task/thread/queue) and swallow+log its own errors internally.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Transactional email
- **Setup:** All outbound email (verification/reset links, receipts, invites, notifications) goes through the shared `EmailSender` seam (`templates/components/security/auth/_core.py`) — build an `EmailMessage(to, subject, body)` (plain text) and call the block's injected sender. FastAPI uses `SmtpEmailSender` (stdlib `smtplib`, fire-and-forget via `asyncio.create_task`); Django uses `DjangoEmailSender` (Django's own `EMAIL_BACKEND`, fire-and-forget via a bounded `ThreadPoolExecutor` — never `asyncio.create_task`, which silently drops delivery under `async_to_sync`). `send()` never raises and never blocks the caller on the network round-trip — a delivery failure is logged, not propagated.
- **Secrets:** `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM` (FastAPI) or the Django `EMAIL_BACKEND`'s equivalent settings — resolved via `secret_store.py` (env first, AWS Secrets Manager fallback); required in every non-dev environment or delivery silently falls back to the dev-only console sender.
- **Maintenance:** Keep new transactional email on this one seam rather than adding a second email client — a new provider (SES, Postmark) is a new `EmailSender` implementation behind the same Protocol, not a parallel code path.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34). Composes the
existing auth component's EmailSender seam and its two framework adapters
only — no new infrastructure. The Django ThreadPoolExecutor-vs-asyncio.
create_task lesson is cited verbatim from DjangoEmailSender's own docstring
in templates/backend/django/core/security/auth/stores.py.
-->
