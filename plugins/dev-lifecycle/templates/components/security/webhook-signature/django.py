"""Django wiring for the webhook-signature component: a view decorator that
reads the RAW request body and verifies it via `_core.verify()`. Canon:
references/security/payments-security.md ("Webhook signature verification").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/webhook_signature/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`.

Django only (`django`) -- no third-party dependency.
"""

from __future__ import annotations

import functools
import logging
from typing import Callable

import _core
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest

logger = logging.getLogger(__name__)


def require_webhook_signature(
    secret_getter: Callable[[], str],
    *,
    header_name: str = "HTTP_STRIPE_SIGNATURE",
    tolerance_s: int = 300,
) -> Callable:
    """Decorator factory for a Django view function:
    `@require_webhook_signature(lambda: get_secret("STRIPE_WEBHOOK_SECRET"))`.

    `request.body` is Django's own raw-bytes attribute -- reading it here,
    before the view ever touches `request.POST` or a DRF-style
    `request.data`, is what keeps this the RAW body the sender actually
    signed. `header_name` is the `request.META` key, not the HTTP header
    name -- Django maps `Stripe-Signature` to `HTTP_STRIPE_SIGNATURE`
    (uppercase, hyphens to underscores, `HTTP_` prefix); pass the `META`
    form directly rather than this decorator guessing the mapping.

    `secret_getter` is a zero-arg callable, resolved fresh per request --
    see fastapi.py's counterpart docstring for why (secret rotation without
    a redeploy).

    On failure, returns `HttpResponseBadRequest` with a generic body (never
    distinguishing failure reasons in the response) and logs the failure by
    exception TYPE only via the module logger -- never the header or
    secret value. On success, the view function is called normally and
    receives the same `request` (with `request.body` already read and
    Django-cached, so the view's own access to it is unaffected)."""

    def decorator(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @functools.wraps(view_func)
        def wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            raw_body = request.body
            signature_header = request.META.get(header_name)
            try:
                _core.verify(raw_body, signature_header, secret_getter(), tolerance_s=tolerance_s)
            except _core.WebhookVerificationError as exc:
                logger.warning("webhook signature verification failed: %s", type(exc).__name__)
                return HttpResponseBadRequest("invalid webhook signature")
            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator
