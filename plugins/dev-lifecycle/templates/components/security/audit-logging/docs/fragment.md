<!-- fragment: block:components/security/audit-logging -->

## Setup
Copy `audit.py` into `app/core/security/audit.py`. Ensure the app's logging
config doesn't filter the `audit` logger below `INFO` — its output is a
required audit trail, not debug noise. Call `audit_event(...)` at every
authentication success/failure, authorization denial, privilege change, and
admin action. If a per-framework request middleware exists (Step 3), have it
call `bind_request_id(...)` once per request so every event in that request
carries the same id automatically.

## Maintenance
`DEFAULT_SENSITIVE_KEYS` is the redaction floor, not a ceiling — extend it
per call site (`sensitive_keys=DEFAULT_SENSITIVE_KEYS | {"your_field"}`) when
a domain-specific field needs withholding too; never shrink it.
