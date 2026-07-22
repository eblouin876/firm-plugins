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

`redact()` replaces any key matching `sensitive_keys` (case-insensitive
exact match on the key name) with `REDACTED`, recursing into nested
mappings. `DEFAULT_SENSITIVE_KEYS` covers the common credential/PII-adjacent
key names (`password`, `token`, `api_key`, `ssn`, `card_number`, ...) — pass
`sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"your_field"}` at a call site to
extend it for a domain-specific field, never to shrink it. Redaction does
**not** descend into lists of dicts — keep `extra` payloads flat rather than
relying on it to reach inside a list.

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
input), and — the load-bearing test — that a redacted value **never reaches
the actual log line's text**, not just the returned record.

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
- **Redaction doesn't descend into lists.** Recursing into arbitrarily nested
  lists-of-dicts adds real complexity for a case `extra` shouldn't need if
  callers keep it flat (documented above) — accepted as a documented limit
  rather than building it out unused.
