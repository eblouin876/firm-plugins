"""Framework-neutral security-header policy and builder: HSTS, X-Content-Type-
Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, and a CSP
builder with a strict default and an explicit relaxation API. Canon:
references/security/secure-baseline.md ("Security headers & CSP" — set on
every response by default, middleware not per-route opt-in; start CSP
restrictive with `default-src 'self'`, no unsafe-inline/unsafe-eval without a
documented reason).

Drop-in: copy this file into app/core/security/security_headers/_core.py
(keep it alongside fastapi.py/django.py from the same directory — see the
note at the top of each of those files). Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

# ---------------------------------------------------------------------------
# CSP
# ---------------------------------------------------------------------------

# Strict-by-default: only the app's own origin may supply anything, no
# plugins/objects, and no framing (belt-and-suspenders with X-Frame-Options
# below, since `frame-ancestors` is the CSP-native equivalent and takes
# precedence in browsers that honor both). A project that needs to load a
# CDN script, an embedded widget, etc. calls `.allow(directive, *sources)` to
# relax exactly the directive it needs — the default never widens on its own.
_DEFAULT_CSP_DIRECTIVES: Mapping[str, tuple[str, ...]] = {
    "default-src": ("'self'",),
    "base-uri": ("'self'",),
    "object-src": ("'none'",),
    "frame-ancestors": ("'none'",),
}


@dataclass(frozen=True, slots=True)
class CSPPolicy:
    """Immutable CSP directive set. Construct via `CSPPolicy()` for the
    strict default, then relax explicitly with `.allow(directive, *sources)`
    — never mutate the default in place, so a call site can't accidentally
    widen the shared default for every other consumer of this module."""

    directives: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(_DEFAULT_CSP_DIRECTIVES)
    )

    def allow(self, directive: str, *sources: str) -> "CSPPolicy":
        """Return a NEW policy with `sources` appended to `directive`
        (creating it if absent), added to whatever the directive already
        allows — e.g. `CSPPolicy().allow("script-src", "'self'",
        "https://cdn.example.com")`. Deliberately additive, not a
        set/override: relaxing one directive should not silently drop an
        existing constraint on it."""
        existing = self.directives.get(directive, ())
        merged = tuple(dict.fromkeys((*existing, *sources)))  # de-dup, keep order
        new_directives = dict(self.directives)
        new_directives[directive] = merged
        return replace(self, directives=new_directives)

    def build(self) -> str:
        """Renders the `Content-Security-Policy` header value. Directive
        order follows insertion order (Python dict) so output is stable and
        deterministic across calls — useful for tests and for diffing a
        header change in review."""
        return "; ".join(
            f"{directive} {' '.join(sources)}" if sources else directive
            for directive, sources in self.directives.items()
        )


# ---------------------------------------------------------------------------
# Permissions-Policy
# ---------------------------------------------------------------------------

# Minimal-by-default: every commonly-abused/tracking-adjacent feature is
# denied to every origin (an empty allowlist `()`  -> `feature=()`), not
# merely left unset. A project that genuinely uses camera/mic/geolocation
# widens the specific feature it needs via `security_headers=security_headers.
# replace(...)` or by constructing its own dict — see the component README.
_DEFAULT_PERMISSIONS_POLICY: Mapping[str, tuple[str, ...]] = {
    "camera": (),
    "microphone": (),
    "geolocation": (),
    "browsing-topics": (),
    "interest-cohort": (),
}


def _build_permissions_policy(features: Mapping[str, tuple[str, ...]]) -> str:
    def _render(allowlist: tuple[str, ...]) -> str:
        return "(" + " ".join(allowlist) + ")"

    return ", ".join(f"{feature}={_render(allowlist)}" for feature, allowlist in features.items())


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SecurityHeadersPolicy:
    """The full header set this component builds. Construct with defaults
    for the secure-baseline posture; override individual fields (via
    `dataclasses.replace`) for a documented, deliberate exception — never by
    editing this class's defaults in place."""

    hsts_max_age: int = 31_536_000  # 1 year — the commonly-cited sensible floor for a real HSTS rollout
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False  # preload is a one-way door (hsts-preload list); opt in deliberately, not by default
    frame_options: str = "DENY"
    referrer_policy: str = "strict-origin-when-cross-origin"
    permissions_policy: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(_DEFAULT_PERMISSIONS_POLICY)
    )
    csp: CSPPolicy = field(default_factory=CSPPolicy)

    def _hsts_value(self) -> str:
        parts = [f"max-age={self.hsts_max_age}"]
        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")
        if self.hsts_preload:
            parts.append("preload")
        return "; ".join(parts)

    def build_headers(self, *, is_https: bool) -> dict[str, str]:
        """Returns the header dict to set on every outbound response.
        `is_https` gates HSTS only — HSTS on a plaintext response is
        meaningless (a MITM on that same plaintext connection can strip it
        before it's ever honored) and some browsers treat an HSTS header
        over HTTP as a no-op or a signal to ignore; local dev over
        plain HTTP simply never receives the header, which is correct, not
        a gap. Every other header is set unconditionally — none of them
        assume TLS."""
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": self.frame_options,
            "Referrer-Policy": self.referrer_policy,
            "Permissions-Policy": _build_permissions_policy(self.permissions_policy),
            "Content-Security-Policy": self.csp.build(),
        }
        if is_https:
            headers["Strict-Transport-Security"] = self._hsts_value()
        return headers


DEFAULT_POLICY = SecurityHeadersPolicy()
