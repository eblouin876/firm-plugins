# Vendored from templates/components/security/cors-lockdown (_core.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.

"""Framework-neutral CORS policy: an explicit-allowlist object that refuses
to construct a wildcard-plus-credentials configuration, plus the two
translation functions each framework adapter uses to wire it up. Canon:
references/security/secure-baseline.md ("CORS lockdown" — explicit allowlist
of origins, never `*` combined with `credentials: true`; only allow the
methods/headers actually needed).

Drop-in: copy this file into app/core/security/cors_lockdown/_core.py (keep
it alongside fastapi.py/django.py from the same directory). Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InsecureCORSPolicyError(ValueError):
    """Raised at CORSPolicy construction time when the requested
    configuration is insecure by this component's own stricter-than-baseline
    rule: no wildcard origin at all (not just "no wildcard with
    credentials") -- see the component README's "Judgment calls" for why
    the bar here is set above the baseline's literal minimum."""


@dataclass(frozen=True, slots=True)
class CORSPolicy:
    """An explicit-allowlist CORS policy. `allow_origins` is REQUIRED and
    must be a non-empty, wildcard-free tuple -- there is no default that
    permits "any origin", by design (see InsecureCORSPolicyError below).
    Construct one per environment (dev/staging/prod get distinct instances
    with distinct origin lists), never one shared list across all three."""

    allow_origins: tuple[str, ...]
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = ("GET", "HEAD", "POST")
    allow_headers: tuple[str, ...] = ("Content-Type", "Authorization")
    max_age: int = 600

    def __post_init__(self) -> None:
        if not self.allow_origins:
            raise InsecureCORSPolicyError(
                "CORSPolicy requires a non-empty allow_origins list -- there is no "
                "default that permits any origin; pass the exact origin(s) this "
                "environment's frontend is served from."
            )
        if "*" in self.allow_origins:
            # Stricter than the baseline's literal minimum ("never wildcard
            # WITH credentials"): this component rejects a bare wildcard
            # origin outright, credentials or not. An explicit-allowlist
            # component that still permits "any origin" for the
            # no-credentials case has quietly defeated its own purpose --
            # see the README's "Judgment calls".
            raise InsecureCORSPolicyError(
                "CORSPolicy does not permit a wildcard '*' origin, with or without "
                "credentials -- pass the exact origin(s) to allow. If every origin "
                "genuinely must be allowed and no credentials/cookies are ever sent, "
                "that is a public, unauthenticated API and does not need this "
                "component's allowlist model at all."
            )
        if any(origin.strip() == "" for origin in self.allow_origins):
            # Rejected unconditionally, not only when allow_credentials=True
            # -- a blank origin entry is never meaningful (it can't match a
            # real `Origin` header) regardless of the credentials setting,
            # so gating this check on allow_credentials only caught the
            # narrower, credentials-specific case and let a blank entry
            # slip through silently for a no-credentials policy.
            raise InsecureCORSPolicyError("CORSPolicy origins must not contain a blank entry")

    def to_starlette_kwargs(self) -> dict:
        """The exact kwargs Starlette's own `CORSMiddleware.__init__`
        accepts -- this policy is a thin, validated front-end for that
        middleware's config, not a reimplementation of CORS handling."""
        return {
            "allow_origins": list(self.allow_origins),
            "allow_credentials": self.allow_credentials,
            "allow_methods": list(self.allow_methods),
            "allow_headers": list(self.allow_headers),
            "max_age": self.max_age,
        }

    def to_django_cors_headers_settings(self) -> dict:
        """The settings dict `django-cors-headers` (the Django convention
        for CORS -- see the component README's NEEDS) reads. A caller
        merges this into settings.py, e.g. `globals().update(policy.
        to_django_cors_headers_settings())`, rather than hand-writing these
        names and risking drift from the policy object."""
        return {
            "CORS_ALLOWED_ORIGINS": list(self.allow_origins),
            "CORS_ALLOW_CREDENTIALS": self.allow_credentials,
            "CORS_ALLOW_METHODS": list(self.allow_methods),
            "CORS_ALLOW_HEADERS": [h.lower() for h in self.allow_headers],
            "CORS_PREFLIGHT_MAX_AGE": self.max_age,
        }
