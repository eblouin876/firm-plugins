<!--
recipe: audit-logging
applies-to:
  - backend block: fastapi OR django (framework-neutral component, two vendored copies)
last-verified: 2026-07-23
provenance: manual
sources:
  - references/security/secure-baseline.md
  - references/security/data-protection.md
  - templates/components/security/audit-logging/README.md
-->

# Audit logging

Wire the existing `audit-logging` catalog component into a feature so every security-relevant action it performs (auth event, admin action, access to restricted data) leaves a structured, redacted, queryable trail. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- What to audit (and what not to)
- Doc fragment

## What this wires
Applying this recipe gives a feature a durable "who did what to which record, when" trail: one `audit_event(...)` call per security-relevant action, emitted as a single structured JSON line on the stdlib `audit` logger, with sensitive fields redacted before they're ever serialized.

It **composes an existing piece** — it invents no new infrastructure:
- **`templates/components/security/audit-logging/`** — the framework-neutral catalog component (`audit.py`: `audit_event`, `redact`, `bind_request_id`/`reset_request_id`, `DEFAULT_SENSITIVE_KEYS`, `REDACTED`). This is the canon copy; a backend block vendors it verbatim.
- **The vendored copy already in each backend block** — `templates/backend/fastapi/app/core/security/audit_logging/audit.py` and `templates/backend/django/core/security/audit_logging/audit.py`, each paired with a `middleware.py` (`RequestIDMiddleware` for FastAPI, the Django equivalent) that calls `bind_request_id(...)` once per request so every `audit_event()` call downstream automatically carries the same `request_id`.
- **The worked example already in the kit**: `templates/backend/fastapi/app/api/routers/admin.py` calls `audit_event("admin.user.suspend", actor=claims.sub, resource=f"user:{user.id}", outcome="success", changed_fields=["status"])` (and the matching `ban`/`reinstate`/role-change handlers) — copy this shape for a new feature's own admin/privileged actions. `templates/components/security/auth/_core.py`'s `AuthEventSink` Protocol is the auth-flow equivalent; `templates/backend/fastapi/app/core/security/auth/stores.py`'s `AuditAuthEventSink` (and the Django track's identical shim) is the adapter that forwards `AccountService`'s login/register/verify/reset events into `audit_event(...)` — a second worked example, this time for auth rather than admin actions.

## Prerequisites
- A backend block (`templates/backend/fastapi` or `templates/backend/django`) with `audit.py` already vendored under `app/core/security/audit_logging/` — every backend block in this kit ships it by default, so this is normally already true.
- The app's logging configuration does not filter the `audit` logger below `INFO` — its output is the audit trail, not debug noise.
- If request-level correlation is wanted (usually yes), the block's `RequestIDMiddleware` (or the Django equivalent) is mounted so `bind_request_id(...)` runs at the top of every request.
- No version-sensitive dependency: the component is stdlib-only (`logging`, `contextvars`, `json`), so there is no `references/compatibility-matrix.md` row to pin against.

## Wire-up steps
1. **Identify the security-relevant actions in the feature.** Per `references/security/secure-baseline.md`'s "Audit logging" section: authentication successes/failures, authorization denials, privilege/role changes, administrative actions, and access to restricted-tier data (who viewed/exported which record). A CRUD endpoint that only touches the acting user's own ordinary data does not need an audit event for every request — reserve it for actions with a real audit-worthy consequence.

2. **Call `audit_event(action, *, actor, resource, outcome, **extra)` at each of those points**, importing it from the block's vendored copy (`from app.core.security.audit_logging.audit import audit_event` — FastAPI; the Django track's import path mirrors it). Follow the schema, not free text:
   - `action` — a short verb phrase, `"<domain>.<entity>.<verb>"` (e.g. `"admin.user.suspend"`, `"invoice.export"`, `"role.grant"`), matching the existing `admin.user.*` actions in `app/api/routers/admin.py`.
   - `actor` — an identifier only (`claims.sub`, a service-account name, `"system"` for an automated action) — never a full user object.
   - `resource` — a type+id identifier (`f"user:{user.id}"`, `f"invoice:{invoice.id}"`) — never the record's data.
   - `outcome` — one of `"success"` / `"failure"` / `"denied"` (or a small project-specific closed set) — not free text.
   - `**extra` — `changed_fields` (names only, never old/new PII values), `ip`, `method`/`endpoint` for an HTTP-triggered action — whatever's worth recording beyond the required fields.

3. **Never pass a PII payload or a secret expecting it to be withheld only by luck.** `redact()` (used internally by `audit_event`) replaces any key matching `DEFAULT_SENSITIVE_KEYS` — case-insensitive exact match plus a bounded substring match (`secret`, `token`, `password`, `passwd`, `private_key`) — with `REDACTED`, recursing into nested mappings and into mappings nested inside lists/tuples. This is the **redaction floor, not a ceiling**: don't rely on it as the only reason a raw password/token/full PII payload never reaches a call site's `**extra` in the first place — the floor exists in case one slips through, not as license to pass one deliberately.

4. **Extend the redaction set per call site when a domain-specific field needs withholding too**, never shrink it: `audit_event(..., sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"ssn_last4"})`.

5. **Rely on `bind_request_id`'s ambient binding rather than threading `request_id` through every call.** If the block's `RequestIDMiddleware` (FastAPI: `app/core/security/audit_logging/middleware.py`; Django: the equivalent) is mounted, every `audit_event()` call inside that request already carries the same `request_id` via the `contextvars` fallback — pass `request_id=` explicitly only for an out-of-request call (a background job, a CLI script).

6. **Verify** by triggering the new action and confirming the emitted `audit` log line: exact schema keys (`ts`, `action`, `actor`, `resource`, `outcome`, `request_id`, `extra`), a redacted value never reaching the raw log text (not just the returned dict), and `request_id` populated when the action ran inside a request.

## What to audit (and what not to)
- **Audit**: authentication successes/failures, authorization denials, privilege/role changes, admin actions, access to or export of restricted-tier data.
- **Never pass**: a full PII payload, a password/token/secret, or a free-text field a caller might paste unbounded user-supplied content into — `actor`/`resource` are documented as identifiers, not enforced as such at the type level (both are plain `str`), so the call site is the actual enforcement point.
- **The ids-only rule is the whole point**: `actor`/`resource` name *who* and *what*, never the record's own data — an audit log that can answer "who did what to which record, when" for every transaction is complete without ever holding a PII payload itself.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Audit logging
- **Setup:** Security-relevant actions (auth events, admin actions, privilege changes, access to restricted data) call `audit_event(action, actor=..., resource=..., outcome=..., **extra)` from the vendored `app/core/security/audit_logging/audit.py`. `action` is a short verb phrase (`"admin.user.suspend"`); `actor`/`resource` are identifiers only, never full objects or PII. `RequestIDMiddleware` binds a per-request id so every event in a request is correlated automatically. See `app/api/routers/admin.py` for the worked example.
- **Secrets:** none — the component is stdlib-only.
- **Maintenance:** `DEFAULT_SENSITIVE_KEYS` (in `audit.py`) is the redaction floor for `**extra`, not a ceiling — extend it per call site (`sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"your_field"}`) when a domain-specific field needs withholding too; never shrink it. Ensure the app's logging config never filters the `audit` logger below `INFO`.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34). Composes the
existing catalog component only — no new infrastructure. The FastAPI admin
router and the auth component's AuthEventSink/AuditAuthEventSink adapter are
cited as the kit's own worked examples, per the audit-logging component's
README and references/security/secure-baseline.md's "Audit logging" section.
-->
