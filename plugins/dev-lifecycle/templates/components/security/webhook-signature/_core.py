"""Framework-neutral webhook signature verification: HMAC-SHA256 over the
RAW request body, a replay-window timestamp tolerance, and a constant-time
comparison (`hmac.compare_digest`) -- plus a parser for Stripe's
`t=...,v1=...` reference header format. Canon:
references/security/payments-security.md ("Webhook signature verification"
-- verify every webhook's signature before trusting the payload, reject on
failure, read the RAW body since a parsed/re-serialized body won't match).

Drop-in: copy this file into app/core/security/webhook_signature/_core.py
(keep it alongside fastapi.py/django.py from the same directory). Stdlib
only (`hmac`, `hashlib`, `time`).

Never logs a signature or secret VALUE -- every exception message and log
line below carries only shapes/counts/timing deltas, never the header
string, the computed digest, or the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass

# A candidate signature must be pure lowercase-or-uppercase hex -- the shape
# an HMAC-SHA256 hexdigest always is. Enforced before any
# `hmac.compare_digest` call over a header-supplied candidate: `compare_digest`
# raises `TypeError` for a non-ASCII `str` argument (CPython restricts str
# comparison to ASCII-only), which would otherwise surface as an unhandled
# 500 the moment a webhook sender (or an attacker probing the endpoint)
# sends a `v1=` value containing a non-hex/non-ASCII character.
_HEX_CANDIDATE_PATTERN = re.compile(r"^[0-9a-fA-F]+$")


class WebhookVerificationError(Exception):
    """Base class for every verification failure this module raises. A
    caller (a FastAPI dependency, a Django decorator) catches this one type
    to return a uniform 400/401 -- the specific subtype is for logging/
    debugging, not for choosing a different HTTP status per reason (leaking
    "your timestamp was stale" vs. "your signature was wrong" to the caller
    is its own small information disclosure a legitimate integration never
    needs to distinguish from the outside)."""


class MissingSignatureHeaderError(WebhookVerificationError):
    pass


class MalformedSignatureHeaderError(WebhookVerificationError):
    pass


class TimestampToleranceError(WebhookVerificationError):
    """Raised when the signed timestamp is outside `tolerance_s` of `now`
    -- either a genuinely stale/replayed delivery, or (rarely) significant
    clock drift on one side. Message carries the delta in seconds, never
    the raw signature."""


class SignatureMismatchError(WebhookVerificationError):
    """Raised when no candidate signature in the header matches the
    locally computed one, via `hmac.compare_digest` (constant-time -- see
    `verify()`). Message never carries the signature value on either
    side."""


@dataclass(frozen=True, slots=True)
class ParsedSignatureHeader:
    timestamp: int
    signatures: tuple[str, ...]  # multiple v1= entries supported (key rotation)


def parse_stripe_style_header(header: str) -> ParsedSignatureHeader:
    """Parses Stripe's reference format: comma-separated `key=value` pairs,
    exactly one `t=<unix timestamp>` and one-or-more `v1=<hex hmac>`
    (Stripe sends multiple `v1=` entries during signing-secret rotation --
    every one is a candidate to check against). Any other scheme prefix
    (Stripe also sends `v0=` for an older, deprecated scheme) is ignored,
    matching Stripe's own documented behavior of verifying only `v1`.

    Raises MalformedSignatureHeaderError on anything that doesn't parse:
    no `t=`, a non-integer timestamp, or zero `v1=` entries."""
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise MalformedSignatureHeaderError(
                    "webhook signature header's timestamp ('t=') is not an integer"
                ) from exc
        elif key == "v1":
            signatures.append(value)
    if timestamp is None:
        raise MalformedSignatureHeaderError("webhook signature header is missing 't=<timestamp>'")
    if not signatures:
        raise MalformedSignatureHeaderError("webhook signature header has no 'v1=<signature>' entries")
    return ParsedSignatureHeader(timestamp=timestamp, signatures=tuple(signatures))


def compute_signature(secret: str, timestamp: int, raw_body: bytes) -> str:
    """The Stripe-style signed payload: `"{timestamp}.".encode() +
    raw_body`, HMAC-SHA256, hex-encoded. Exposed standalone so a caller can
    compute what a valid signature would be (e.g. for a test fixture, or to
    sign an outbound webhook this app itself sends to another service using
    the same scheme)."""
    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def verify(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
    *,
    tolerance_s: int = 300,
    now: int | None = None,
) -> None:
    """Verifies `signature_header` (Stripe-style `t=...,v1=...`) against
    `raw_body` and `secret`. Raises a `WebhookVerificationError` subtype on
    any failure; returns `None` (no value to return -- the point is the
    absence of an exception) on success.

    `raw_body` MUST be the exact bytes read off the wire, before any JSON
    parsing/re-serialization -- a parsed-then-re-serialized body will not
    reproduce the same bytes the sender signed (key ordering, whitespace,
    unicode escaping can all differ), and verification will fail even for a
    genuine, unmodified payload. Both framework adapters read the raw body
    first, deliberately ahead of any body-parsing step.

    `tolerance_s` bounds the replay window: a timestamp more than
    `tolerance_s` seconds away from `now` (in EITHER direction -- a
    timestamp claiming to be from the future is just as suspicious as a
    stale one) fails closed with `TimestampToleranceError`.

    Every candidate signature in the header (supporting multiple `v1=`
    entries during a secret rotation) is checked via
    `hmac.compare_digest` -- constant-time, so an attacker measuring
    response timing cannot use it to guess the correct signature one byte
    at a time. A single match is sufficient. A candidate that isn't
    pure hex (e.g. non-ASCII bytes) can never equal a hex digest, so it is
    skipped rather than handed to `hmac.compare_digest` -- see
    `_HEX_CANDIDATE_PATTERN`'s module-level comment for why: passing a
    non-ASCII `str` to `compare_digest` raises `TypeError`, not a clean
    verification failure."""
    if not secret or not secret.strip():
        # An empty/blank secret must never be treated as "no secret
        # configured, so allow everything" (fail OPEN) -- raise before any
        # HMAC is computed, so a deployer's missing/blank secret env var
        # rejects every webhook instead of silently accepting all of them.
        raise WebhookVerificationError("empty webhook secret")

    if not signature_header:
        raise MissingSignatureHeaderError("webhook request is missing its signature header")

    parsed = parse_stripe_style_header(signature_header)

    resolved_now = now if now is not None else int(time.time())
    delta = abs(resolved_now - parsed.timestamp)
    if delta > tolerance_s:
        raise TimestampToleranceError(
            f"webhook timestamp is {delta}s outside the {tolerance_s}s tolerance window"
        )

    expected = compute_signature(secret, parsed.timestamp, raw_body)
    matched = False
    for candidate in parsed.signatures:
        if not _HEX_CANDIDATE_PATTERN.match(candidate):
            continue
        if hmac.compare_digest(expected, candidate):
            matched = True
            break
    if not matched:
        raise SignatureMismatchError("no candidate signature in the header matched")
