<!--
block: components/security/audit-logging  # catalog component
needs:
  - stdlib logging configured: app owns handlers/shipping for the "audit" logger
  - a request-id source (optional): per-framework middleware calling bind_request_id()
exposes:
  - audit_event(action, *, actor, resource, outcome, request_id=None, **extra) -> dict
  - redact(payload, *, sensitive_keys=DEFAULT_SENSITIVE_KEYS) -> dict
  - bind_request_id(request_id) / reset_request_id(token)
  - DEFAULT_SENSITIVE_KEYS, REDACTED
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# audit-logging

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A framework-neutral, drop-in `audit.py`: a structured JSON audit logger built
entirely on stdlib `logging` and `contextvars` — no third-party dependency.
Lives at `templates/components/security/audit-logging/` in this repo; Stage
3-4 backend blocks copy `audit.py` verbatim into
`app/core/security/audit.py`. Embodies the "Audit logging" section of
`references/security/secure-baseline.md` and the "Access control & logging"
section of `references/security/data-protection.md`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- The stable schema
- What belongs in an audit event
- Redaction
- Request-id binding (for Step 3 middleware)
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Stdlib logging configured** — this module calls
  `logging.getLogger("audit").info(...)`; it does not attach handlers or
  configure formatting itself. A consuming app's own logging setup (root
  handler, JSON formatter or plain, log level) decides where the `audit`
  logger's output actually lands. In prod that's normally stdout, captured by
  the container platform's log driver into CloudWatch/an aggregator — no
  extra wiring beyond making sure the `audit` logger isn't filtered below
  `INFO`.
- **A request-id source (optional)** — `bind_request_id()` is a hook, not a
  requirement. Without a caller setting it (typically per-framework request
  middleware landing in Step 3/Stage 3-4), every event's `request_id` is
  `None` — a valid, degraded state, not an error.

**EXPOSES**
- `audit_event(action, *, actor, resource, outcome, request_id=None,
  sensitive_keys=DEFAULT_SENSITIVE_KEYS, **extra) -> dict` — emits one JSON
  line on the `audit` logger and returns the record it emitted.
- `redact(payload, *, sensitive_keys=DEFAULT_SENSITIVE_KEYS) -> dict` — the
  redaction helper `audit_event()` uses internally, also usable standalone
  (e.g. to redact a payload before handing it to a different sink).
- `bind_request_id(request_id) -> Token` / `reset_request_id(token)` — the
  contextvars-based hook a framework's request middleware calls once per
  request so every `audit_event()` call inside that request automatically
  carries the same id, without threading it through every call site by hand.
- `DEFAULT_SENSITIVE_KEYS: frozenset[str]`, `REDACTED: str` — the default
  redaction key set and the sentinel string that replaces a redacted value.
- Its co-located doc fragment: `docs/fragment.md`.

## The stable schema

Every emitted record has exactly these keys: `ts` (ISO-8601 UTC), `action`,
`actor`, `resource`, `outcome`, `request_id`, `extra`. This shape is stable
across every call site in an app — a log consumer (CloudWatch Insights query,
a SIEM ingest rule) can rely on it without per-action special-casing.

- **`action`** — a short verb phrase (`"user.login"`, `"invoice.export"`,
  `"role.grant"`), not a free-text sentence.
- **`actor`** — an identifier (`"user:42"`, `"service:billing-worker"`,
  `"system"` for an automated action) — never a full user object.
- **`resource`** — a type+id identifier (`"invoice:8f21ac"`) — never the
  record's data.
- **`outcome`** — a small closed set (`"success"`, `"failure"`, `"denied"`),
  not free text.
- **`request_id`** — ties an event back to the request that caused it; falls
  back to the `bind_request_id()` contextvar when not passed explicitly.
- **`extra`** — anything else worth recording, redacted per `sensitive_keys`
  before it is ever serialized.

## What belongs in an audit event

Per `references/security/data-protection.md`'s "Access control & logging":
log **who did what to which record, when** — identifiers, not payloads.
Concretely:
- Authentication successes/failures, authorization denials, privilege/role
  changes, administrative actions, and access to restricted-tier data (who
  viewed/exported which record) — per
  `references/security/secure-baseline.md`'s "Audit logging" section.
- `extra` fields worth adding: `changed_fields` (names, not old/new PII
  values), `ip`, `method`/`endpoint` for an HTTP-triggered action.
- **Never**: a full PII payload, a password/token/secret (redaction covers
  the accident, but don't rely on it as the only reason not to pass one — see
  `references/security/data-protection.md`'s minimization principle), or a
  free-text field a caller might paste user-supplied content into unbounded.

## Redaction

`redact()` replaces any key matching `sensitive_keys` with `REDACTED`, via
two layers:

1. **Exact match** (case-insensitive) against `DEFAULT_SENSITIVE_KEYS` —
   the common credential/PII-adjacent key names: `password`, `passwd`,
   `pwd`, `passphrase`, `secret`, `client_secret`, `secret_key`,
   `aws_secret_access_key`, `private_key`, `token`, `access_token`,
   `refresh_token`, `api_key`, `apikey`, `authorization`, `cookie`,
   `set_cookie`, `session_id`, `ssn`, `credit_card`, `card_number`, `cvv`.
   Pass `sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"your_field"}` at a call
   site to extend it for a domain-specific field, never to shrink it.
2. **Bounded substring match** (case-insensitive, always applied — not
   configurable per call site) — a key that *contains* `secret`, `token`,
   `password`, `passwd`, or `private_key` is redacted even if its exact
   name isn't in `DEFAULT_SENSITIVE_KEYS`. This is what catches a call
   site's own naming variant (`stripe_secret_key`, `db_password_hash`,
   `oauth_token_value`) that an exact-match set alone would miss. The
   substring list is deliberately short and specific — not a bare `key` or
   `id` — so it doesn't over-redact ordinary fields.

Redaction recurses into nested mappings, and into mappings nested inside
lists or tuples (e.g. `{"changed": [{"token": "..."}]}` redacts the
`token` inside the list), preserving the original list/tuple structure.
The recursion follows the payload's own nesting with no fixed depth
limit — keep `extra` payloads reasonably shallow as a matter of good
practice, not because redaction stops working at some depth.

## Request-id binding (for Step 3 middleware)

`bind_request_id(request_id)` sets a `contextvars.ContextVar`, correct under
async concurrency (each request's task gets its own copy, unlike a plain
global). A FastAPI/Django middleware landing in Step 3 calls it once at the
top of a request (reading an inbound `X-Request-ID` header or minting a
`uuid4`), and calls `reset_request_id(token)` in a `finally` block so a
reused worker thread/task never leaks the previous request's id into the
next one.

## Testing

`tests/test_audit.py` covers: the stable schema's exact key set, ISO-8601
timestamp validity, that the emitted log line is valid JSON, request-id
resolution (unbound → `None`, contextvar fallback, explicit-argument
override), that `redact()` actually replaces sensitive values
(case-insensitively, recursing into nested dicts, without mutating the
input), every previously-missing `DEFAULT_SENSITIVE_KEYS` entry
(`client_secret`, `secret_key`, `aws_secret_access_key`, `private_key`,
`cookie`, `pwd`, `passphrase`, `authorization`, `set_cookie`,
`access_token`, `refresh_token`, `api_key`), the bounded substring match
catching a naming variant (`stripe_secret_key`, `db_password_hash`,
`SECRET_TOKEN`) without over-redacting an unrelated key (`key`, `user_id`),
recursion into a mapping nested inside a list and inside a tuple
(preserving the sequence type) and through a mixed nested structure, and —
the load-bearing test — that a redacted value **never reaches the actual
log line's text**, not just the returned record.

Run: `uv run --python 3.13 --with pydantic --with pytest -- pytest templates/components/security/audit-logging/tests/ -q`
(`pydantic` isn't imported by this module; the `--with` list matches the
firm-wide verification invocation used across the three Step 2 components).

## Judgment calls

- **No PII in the default schema fields.** `actor`/`resource` are documented
  as identifiers, not enforced as such at the type level (both are plain
  `str`) — a call site can still pass a raw email or name. Enforcing it
  structurally would mean a richer type this module doesn't have visibility
  into (what counts as an "identifier" is app-specific); documenting the
  contract and redacting `extra` is judged the right layer for a stdlib-only
  component, with the fuller check pushed to `code-review`'s security
  dimension per `references/security/attack-surfaces.md`.
- **Redaction now descends into lists/tuples of mappings, unbounded depth.**
  An earlier version of this module treated "redaction doesn't reach inside
  a list" as an acceptable documented limit; a review finding (M4) judged
  that a real call site's `extra` payload is realistically going to include
  a list of changed-field dicts or similar, and a redaction gap there is a
  leak, not a convenience trade-off. The recursion has no depth limit,
  matching the existing Mapping recursion's behavior rather than adding an
  inconsistent cutoff.
- **The substring match list is short and specific on purpose.** `key` and
  `id` were deliberately left off `_SENSITIVE_SUBSTRINGS` even though they
  appear in many credential-adjacent names (`api_key`, `session_id`) —
  those two are already covered by exact matches in `DEFAULT_SENSITIVE_KEYS`
  and are common enough as ordinary field names (`user_id`, `sort_key`)
  that adding them to the substring list would over-redact.
