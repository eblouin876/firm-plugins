"""Django wiring for the idempotency component: a MIDDLEWARE class that is a
no-op for any request without an `Idempotency-Key` header, and otherwise
dedupes via `_core.check()`/`_core.record_response()`. Canon:
references/security/payments-security.md ("Idempotency keys").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/idempotency/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`.

Django only (`django`) -- no third-party dependency, no `redis` import.

Configuration reads Django settings (the Django convention), with an
explicit-kwarg override path for direct instantiation (used by this
component's own tests, and available to a project that wants to construct
this middleware itself rather than configure it via settings), matching
rate-limiting/django.py's pattern: `IDEMPOTENCY_HEADER_NAME` (default
`"HTTP_IDEMPOTENCY_KEY"`, the Django `META` form of `Idempotency-Key` --
see this module's own docstring below for that mapping).

--- `principal_getter` is REQUIRED, and this middleware MUST run AFTER
`AuthenticationMiddleware` (judgment call -- see the component README's
"Principal scoping" section) ---
Django instantiates a `MIDDLEWARE` entry with only `get_response`, so
unlike FastAPI's constructor-kwarg approach, `principal_getter` is resolved
either from an explicit constructor kwarg (direct instantiation) OR from
`settings.IDEMPOTENCY_PRINCIPAL_GETTER` -- a DOTTED IMPORT PATH string
(Django's own convention for a settings value that names a callable, e.g.
`AUTHENTICATION_BACKENDS`), resolved via
`django.utils.module_loading.import_string`. Neither supplied is a hard
`ImproperlyConfigured` at construction time -- there is no default that
silently scopes by "no principal", because that would reintroduce the
exact cross-principal replay this middleware exists to prevent (see
`_core.py`'s module docstring). This module ships `default_principal_getter`
below as the ready-to-use, common-case implementation (authenticated
`request.user.pk`, `None` for anonymous) -- point
`IDEMPOTENCY_PRINCIPAL_GETTER` at it
(`"app.core.security.idempotency.django.default_principal_getter"`) or
write a project-specific one with the same `(request) -> str | None`
shape.

Because `principal_getter` (whether the default or a custom one) typically
reads `request.user`, this middleware MUST be listed in `MIDDLEWARE` AFTER
`"django.contrib.auth.middleware.AuthenticationMiddleware"` -- Django runs
`MIDDLEWARE` top-to-bottom on the request path, so listing this middleware
later means auth has already populated `request.user` by the time this
middleware runs.

**Anonymous-request policy (fail closed, documented, not a silent
default):** if `principal_getter(request)` returns `None`/empty (which
`default_principal_getter` does for `request.user.is_authenticated ==
False`), this middleware treats the request EXACTLY as if it had no
`Idempotency-Key` header at all -- full passthrough, no dedup, no replay,
no storage write. See `fastapi.py`'s identical section for the full
rationale and the explicit per-IP-namespace opt-in pattern for a project
that genuinely needs idempotency protection on anonymous traffic --
never a single shared "anonymous" namespace.
"""

from __future__ import annotations

import logging
from typing import Callable

import _core
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


def default_principal_getter(request: HttpRequest) -> str | None:
    """The common-case `principal_getter`: an authenticated user's primary
    key as a string, or `None` for an anonymous request (triggering the
    default-deny anonymous policy -- see this module's docstring). Point
    `settings.IDEMPOTENCY_PRINCIPAL_GETTER` at
    `"app.core.security.idempotency.django.default_principal_getter"` to
    use this directly, or write a project-specific callable with the same
    `(request) -> str | None` shape for a different notion of "principal"
    (e.g. an API key id for a machine-to-machine endpoint)."""
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return str(user.pk)
    return None

# Same non-cacheable-server-error rule as fastapi.py -- see that file's
# module docstring for the rationale.
_MAX_CACHEABLE_STATUS = 499

_default_store: _core.IdempotencyStore | None = None


def _get_default_store() -> _core.IdempotencyStore:
    """A module-level singleton store, created lazily on first use and
    shared by every request this process handles -- see _core.py's
    `InMemoryIdempotencyStore` docstring for the per-process limitation
    this implies, matching rate-limiting/django.py's identical pattern."""
    global _default_store
    if _default_store is None:
        _default_store = _core.InMemoryIdempotencyStore()
    return _default_store


class IdempotencyMiddleware:
    """New-style Django middleware. `header_name` is the `request.META`
    key, not the HTTP header name -- Django maps `Idempotency-Key` to
    `HTTP_IDEMPOTENCY_KEY` (uppercase, hyphens to underscores, `HTTP_`
    prefix); pass the `META` form directly, matching
    webhook-signature/django.py's `header_name` convention rather than
    this middleware guessing the mapping."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
        *,
        store: _core.IdempotencyStore | None = None,
        principal_getter: Callable[[HttpRequest], str | None] | None = None,
        header_name: str | None = None,
    ) -> None:
        self.get_response = get_response
        self.store = store if store is not None else _get_default_store()
        self.header_name = (
            header_name
            if header_name is not None
            else getattr(settings, "IDEMPOTENCY_HEADER_NAME", "HTTP_IDEMPOTENCY_KEY")
        )
        if principal_getter is not None:
            self.principal_getter = principal_getter
        else:
            setting_path = getattr(settings, "IDEMPOTENCY_PRINCIPAL_GETTER", None)
            if not setting_path:
                raise ImproperlyConfigured(
                    "IdempotencyMiddleware requires a principal_getter -- pass one "
                    "explicitly (principal_getter=...) or set "
                    "IDEMPOTENCY_PRINCIPAL_GETTER in settings.py to a dotted import "
                    "path, e.g. "
                    "'app.core.security.idempotency.django.default_principal_getter'. "
                    "There is no default that scopes by 'no principal' -- that would "
                    "reintroduce cross-user Idempotency-Key replay. This middleware "
                    "must also run AFTER AuthenticationMiddleware in MIDDLEWARE -- "
                    "see this module's docstring."
                )
            self.principal_getter = import_string(setting_path)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raw_key = request.META.get(self.header_name)
        if not raw_key:
            return self.get_response(request)

        principal = self.principal_getter(request)
        if not principal:
            # Anonymous request under the default fail-closed policy: treat
            # exactly like "no Idempotency-Key header" -- see this module's
            # docstring's "Anonymous-request policy" section.
            return self.get_response(request)

        try:
            key = _core.validate_key(raw_key)
        except _core.InvalidIdempotencyKeyError as exc:
            logger.warning("idempotency key rejected: %s", type(exc).__name__)
            return JsonResponse({"detail": "invalid Idempotency-Key"}, status=400)

        raw_body = request.body
        fingerprint = _core.compute_fingerprint(request.method, request.path, raw_body)
        storage_key = _core.compute_storage_key(principal, key)

        try:
            outcome = _core.check(self.store, storage_key, fingerprint)
        except _core.IdempotencyConflictError as exc:
            logger.warning("idempotency conflict: %s", type(exc).__name__)
            return JsonResponse(
                {"detail": "Idempotency-Key was already used for a different request"},
                status=409,
            )

        if outcome.is_replay:
            stored = outcome.stored_response
            assert stored is not None
            response = HttpResponse(stored.body, status=stored.status_code)
            for name, value in stored.headers:
                response[name] = value
            return response

        response = self.get_response(request)

        if response.status_code <= _MAX_CACHEABLE_STATUS:
            _core.record_response(
                self.store,
                storage_key,
                fingerprint,
                _core.StoredResponse(
                    status_code=response.status_code,
                    headers=tuple(response.items()),
                    body=response.content,
                ),
            )

        return response
