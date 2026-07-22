"""Framework-neutral structured JSON audit logging: one JSON object per
audit_event() call on a dedicated `audit` stdlib logger, with configured
sensitive keys redacted before anything is ever serialized or logged.
Canon: references/security/secure-baseline.md ("Audit logging" — actor,
action, resource, outcome, timestamp; never secrets/tokens/full PII) and
references/security/data-protection.md ("Access control & logging" — log
who accessed/exported which record, when; identifiers, not payloads).

Drop-in: copy this file into app/core/security/audit.py. Stdlib only
(`logging`, `contextvars`, `json`) — no framework or third-party
dependency. Per-framework request middleware (Stage 3+ backend blocks)
calls bind_request_id() once per request so every audit_event() emitted
during that request carries the same request id automatically, without
threading it through every call site by hand.
"""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

logger = logging.getLogger("audit")

# Keys whose VALUES are redacted before an audit event is ever serialized
# or logged, regardless of which call site supplied them. Case-insensitive
# exact match on the key name (see _SENSITIVE_SUBSTRINGS below for the
# bounded substring match that catches names not on this exact list). This
# is the floor, not a ceiling — pass `sensitive_keys=` to audit_event() to
# extend it per call site (e.g. a domain-specific field like "ssn_last4" if
# a project wants it withheld too), never to shrink it.
DEFAULT_SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "client_secret",
        "secret_key",
        "aws_secret_access_key",
        "private_key",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set_cookie",
        "session_id",
        "ssn",
        "credit_card",
        "card_number",
        "cvv",
    }
)

# Bounded substring match, applied in addition to the exact-match set above:
# a key CONTAINING one of these substrings (case-insensitive) is redacted
# even if the exact key name isn't in DEFAULT_SENSITIVE_KEYS. This is what
# catches a call site's own naming variant — "stripe_secret_key",
# "db_password_hash", "user_passwd_confirm" — that an exact-match set alone
# would miss. Deliberately short and specific (not e.g. bare "key" or "id",
# which would over-redact): each substring here is itself a strong signal of
# a credential-shaped value, not a common English word.
_SENSITIVE_SUBSTRINGS: Final[tuple[str, ...]] = (
    "secret",
    "token",
    "password",
    "passwd",
    "private_key",
)

REDACTED: Final[str] = "***REDACTED***"


def _is_sensitive_key(key: str, sensitive_keys: frozenset[str]) -> bool:
    """A key is sensitive if it exact-matches `sensitive_keys`
    (case-insensitive) or CONTAINS one of `_SENSITIVE_SUBSTRINGS`
    (case-insensitive) — the bounded substring check that catches a naming
    variant not on the exact list (e.g. "stripe_secret_key")."""
    lowered = key.lower()
    if lowered in sensitive_keys:
        return True
    return any(marker in lowered for marker in _SENSITIVE_SUBSTRINGS)


# Set once per request by per-framework middleware (bind_request_id), read
# by every audit_event() call in that request/task context that doesn't
# pass request_id explicitly. A contextvar (not a global) so it's correct
# under async concurrency — each request's task gets its own copy.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_request_id", default=None
)


def bind_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    """Set the current request id for this context. Called once by
    per-framework request middleware at the top of a request (Stage 3+:
    a FastAPI middleware / Django middleware reading the inbound
    X-Request-ID header or minting a uuid4). Returns a Token — pass it to
    reset_request_id() in a `finally` block to unbind cleanly when the
    request ends, so a worker thread/task reused for the next request
    doesn't leak the previous one's id."""
    return request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    request_id_var.reset(token)


def _redact_value(value: Any, *, sensitive_keys: frozenset[str]) -> Any:
    """Recurse into a value that isn't itself a top-level sensitive key's
    value: a nested Mapping is redacted recursively; a list/tuple is walked
    element-by-element, redacting any Mapping found inside (preserving the
    original sequence type — a list stays a list, a tuple stays a tuple);
    anything else (str, int, a plain non-dict object, ...) is returned
    unchanged. Recursion depth is unbounded — it follows the payload's own
    nesting exactly, the same as the Mapping-only recursion this replaces;
    a pathologically deep `extra` payload is a caller problem, not one this
    helper guards against."""
    if isinstance(value, Mapping):
        return redact(value, sensitive_keys=sensitive_keys)
    if isinstance(value, (list, tuple)):
        redacted_items = [_redact_value(item, sensitive_keys=sensitive_keys) for item in value]
        return type(value)(redacted_items)
    return value


def redact(
    payload: Mapping[str, Any],
    *,
    sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS,
) -> dict[str, Any]:
    """Return a copy of `payload` with any key matching `sensitive_keys`
    (case-insensitive exact match, plus a bounded case-insensitive
    substring match — see `_is_sensitive_key`) replaced by REDACTED.
    Recurses into nested mappings, and into mappings nested inside lists or
    tuples (e.g. `{"changed": [{"token": "..."}]}`), so a sensitive key
    buried anywhere in the payload's own nested shape is still caught — the
    recursion follows the payload's actual structure with no fixed depth
    limit and no special-casing of how deep a mapping or sequence is
    nested. A non-mapping, non-sequence value (a bare `str`, `int`, custom
    object, ...) is returned unchanged since there is no key to redact
    inside it."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if _is_sensitive_key(key, sensitive_keys):
            out[key] = REDACTED
        else:
            out[key] = _redact_value(value, sensitive_keys=sensitive_keys)
    return out


def audit_event(
    action: str,
    *,
    actor: str,
    resource: str,
    outcome: str,
    request_id: str | None = None,
    sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS,
    **extra: Any,
) -> dict[str, Any]:
    """Emit one structured JSON audit log line on the `audit` logger and
    return the emitted record (useful for tests, or for an additional
    outbound audit sink beyond stdlib logging).

    Stable schema every event carries: ts, action, actor, resource,
    outcome, request_id, extra.

    - `action` — what happened, a short verb phrase (e.g. "user.login",
      "invoice.export", "role.grant").
    - `actor` — who did it: a user id, service account name, or "system"
      for an automated action. An identifier, never a full user object.
    - `resource` — what was acted on: a type+id string (e.g.
      "invoice:8f21ac", "user:42") — an identifier, not the record's data.
    - `outcome` — "success", "failure", "denied", or a project-specific
      short enum; keep it a small closed set, not free text.
    - `request_id` — falls back to the ambient contextvar set by
      bind_request_id() when not passed explicitly, so most call sites
      never need to pass it at all.
    - `**extra` — anything else worth recording (e.g. `changed_fields=[...]`,
      `ip=...`). Redacted per `sensitive_keys` before it is ever serialized
      — never pass a raw password/token/secret expecting it to reach the
      log verbatim; it won't, but don't rely on that as the only reason
      not to pass one (see the component README's "What belongs in an
      audit event" section for what NOT to put here at all, e.g. full PII
      payloads).
    """
    resolved_request_id = request_id if request_id is not None else request_id_var.get()
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "action": action,
        "actor": actor,
        "resource": resource,
        "outcome": outcome,
        "request_id": resolved_request_id,
        "extra": redact(extra, sensitive_keys=sensitive_keys),
    }
    logger.info(json.dumps(record, default=str, sort_keys=True))
    return record
