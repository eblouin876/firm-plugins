<!--
library: owasp
versions-covered: "Top 10:2025"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Security review checklist (OWASP Top 10:2025)

Audit every modified code path against these categories. Anchored to the OWASP Top 10:2025 (released Nov 2025), tailored to a React frontend + FastAPI/SQLAlchemy/Postgres backend. Only flag issues actually present in or reachable from the changed code — but trace reachability honestly.

## A01 — Broken Access Control (now includes SSRF)
The #1 risk. For every changed endpoint or data access:
- Is authorization checked, not just authentication? Being logged in ≠ being allowed. Confirm the user may act on *this specific resource*.
- **IDOR:** does the code fetch by an ID from the request without verifying ownership/scope? (`/orders/{id}` must check the order belongs to the caller.)
- Are role/permission checks present on every protected route and enforced server-side (never only hidden in the UI)?
- **SSRF (now under A01):** does the change make outbound requests to a URL derived from user input? If so, is the target validated/allowlisted so it can't be coerced to internal addresses?

## A02 — Security Misconfiguration
- New/changed config: debug mode off in prod, no verbose error pages or stack traces exposed to clients, CORS not overly permissive (no blanket `*` with credentials), security headers intact.
- No default credentials, no unnecessary endpoints/admin surfaces newly exposed.
- Cloud/IaC or framework settings changed safely.

## A03 — Software Supply Chain Failures
- New dependencies added in this change: are they necessary, reputable, pinned? Any typosquat risk or unmaintained package?
- Lockfile updated consistently with manifest. No unexpected transitive bumps.
- No fetching/executing remote code at build or runtime from untrusted sources.

## A04 — Cryptographic Failures
- Sensitive data (passwords, tokens, PII) handled correctly: passwords hashed with a strong adaptive algorithm (bcrypt/argon2), never plaintext, never reversible "encryption" for passwords.
- Secrets from config/env, never hardcoded, never logged. No secrets newly committed.
- TLS for data in transit; correct, modern algorithms; no home-rolled crypto; secure randomness for tokens.

## A05 — Injection (includes XSS)
- **SQL:** all queries parameterized / via the ORM. No string-built SQL with user input. (SQLAlchemy used correctly defends this — flag any raw `text()` with interpolation.)
- **Command/path injection:** no shelling out with unsanitized input; no path traversal from user-controlled filenames.
- **XSS (frontend):** no `dangerouslySetInnerHTML` with unsanitized content; user content rendered as text/escaped; for server-rendered templates, autoescaping on and not bypassed.

## A06 — Insecure Design
- Does the change's approach have a design-level flaw a patch won't fix? Missing rate limiting on sensitive actions, no abuse/anti-automation controls, trust boundaries crossed without validation, business-logic bypasses.

## A07 — Identification & Authentication Failures
- Auth changes: session/token handling correct, tokens validated fully (signature, expiry, issuer/audience), sensible expiry, secure logout/rotation.
- Protection against credential stuffing/brute force on auth endpoints (rate limiting, lockout/backoff).

## A08 — Software & Data Integrity Failures
- Untrusted deserialization (pickle and similar) of user-controlled data — avoid.
- Integrity of updates/critical data; no unsigned/unverified data treated as trusted.

## A09 — Security Logging & Alerting Failures
- Security-relevant events (auth failures, access-control denials, privilege changes) are logged.
- Logs do NOT contain secrets, tokens, passwords, or excessive PII. Errors logged server-side rather than leaked to the client.

## A10 — Mishandling of Exceptional Conditions (new in 2025)
- **Fail closed, not open:** on error/exception, does the code deny access or grant it? A `try/except` around an auth check that proceeds on failure is a vulnerability.
- Exceptions handled deliberately — no bare `except: pass` swallowing security-relevant failures.
- Error responses don't disclose internals (stack traces, SQL, file paths, system info) to the client.
- Edge cases and abnormal inputs handled without entering an exploitable or inconsistent state.

## Cross-cutting: input validation
- All external input (body, query, path, headers, uploads) validated at the boundary — type, range, length, format. On the FastAPI side, Pydantic schemas should enforce this; flag endpoints accepting unvalidated raw input.
- Never trust client-side validation as the security control; the server validates regardless.
