"""FastAPI/Starlette wiring for the webhook-signature component: a
dependency that reads the RAW request body before any JSON parsing and
verifies it via `_core.verify()`. Canon:
references/security/payments-security.md ("Webhook signature verification").

Drop-in: copy this whole directory (this file, `_core.py`, `django.py`)
into app/core/security/webhook_signature/ and keep them together. This file
imports its core logic with a bare `import _core` -- see the
security-headers component's `fastapi.py` for the full rationale.

Starlette/FastAPI only (`starlette`, `fastapi`) -- no third-party
dependency.
"""

from __future__ import annotations

import logging
from typing import Callable

import _core
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def make_webhook_verification_dependency(
    secret_getter: Callable[[], str],
    *,
    header_name: str = "stripe-signature",
    tolerance_s: int = 300,
) -> Callable:
    """Returns a FastAPI dependency: `Depends(make_webhook_verification_
    dependency(lambda: get_secret("STRIPE_WEBHOOK_SECRET")))`. Reads
    `await request.body()` -- Starlette caches the raw body internally, so
    this is safe to call even if the route handler ALSO reads
    `request.body()` or a body-parsing dependency runs afterward; it will
    see the same cached bytes, not a second read of an already-consumed
    stream.

    `secret_getter` is a zero-arg callable (not the secret string itself)
    so the secret is resolved fresh on every call rather than captured
    once at app-startup/dependency-construction time -- correct even if a
    project rotates the webhook secret via `secret_store.get_secret()`
    without a redeploy.

    Returns the dependency's own return value as the verified raw body
    bytes, so a route handler that also needs the parsed payload does its
    own `json.loads(raw_body)` -- this dependency deliberately does not
    parse JSON itself; verification and parsing are separate concerns, and
    a handler that only needs to acknowledge receipt (the common webhook
    pattern: 2xx immediately, process async) never needs the parsed form
    at all.

    On any `_core.WebhookVerificationError`, raises `HTTPException(400)`
    with a caller-safe generic detail message -- never distinguishing
    "missing header" from "bad signature" from "stale timestamp" in the
    response, and the failure is logged (see `_core.py`'s module docstring)
    by exception TYPE only, never by header/signature value."""

    async def verify_webhook_signature(request: Request) -> bytes:
        raw_body = await request.body()
        signature_header = request.headers.get(header_name)
        try:
            _core.verify(raw_body, signature_header, secret_getter(), tolerance_s=tolerance_s)
        except _core.WebhookVerificationError as exc:
            logger.warning("webhook signature verification failed: %s", type(exc).__name__)
            raise HTTPException(status_code=400, detail="invalid webhook signature") from exc
        return raw_body

    return verify_webhook_signature
