<!--
block: components/security/secrets-loading  # catalog component
needs:
  - process env: reads secret VALUES only from os.environ — the process env is the interface (12-factor); this module refuses to parse .env itself
  - AWS Secrets Manager (optional, opt-in): SECRETS_BACKEND=aws-secrets-manager enables a fallback lookup layer; requires boto3 installed (lazily imported, not a hard dependency) and IAM read access to the secret(s)
exposes:
  - get_secret(name, *, required=True, default=None) -> str | None — the single typed accessor every consumer calls instead of os.environ.get() directly
  - validate_required(names) -> None — startup fail-fast check, raises MissingSecretsError listing every missing secret at once
  - SecretNotFoundError / MissingSecretsError / SecretShapeError — the exception types callers catch
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# secrets-loading

A framework-neutral, drop-in `secret_store.py`: layered secret resolution
(process env first, an optional AWS Secrets Manager fallback second), a
single typed accessor, a startup fail-fast validator, and a hard rule
against ever logging a secret's value. Lives at
`templates/components/security/secrets-loading/` in this repo; Stage 3-4
backend blocks copy `secret_store.py` verbatim into
`app/core/security/secret_store.py`. Embodies
`references/security/secrets-management.md` and the "Secrets never in code
or images" section of `references/security/secure-baseline.md` — this
component is the mechanism, those docs are the canon it's grounded in.

**Named `secret_store.py`, not `secrets.py`:** this module provides no
stdlib-`secrets`-module functionality (no token/password generation) — the
shadow of a security-critical stdlib module's name is pure downside once
this file lands on a project's import path, especially ahead of Stages 3-4
hard-coding `from app.core.security.secret_store import ...` across the
generated backend. See "Judgment calls" for the fuller rationale.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block — it declares what it needs/exposes but skips
the full block placement and per-stack directory conventions.

## Contents
- Composition contract
- Why no `.env` parsing
- Layered resolution
- The AWS Secrets Manager path
- Never logs values
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Process env** — `get_secret()`'s first (and only required) layer. The
  module reads `os.environ` directly; it never opens or parses a `.env` file
  itself (see "Why no `.env` parsing" below). A consuming project supplies
  the process env however it already does — the framework's own loader for
  local dev, GitHub Actions encrypted secrets in CI, ECS task-definition
  `secrets` blocks in prod — per `references/security/secrets-management.md`'s
  Local vs CI vs prod table.
- **AWS Secrets Manager (optional)** — only consulted when
  `SECRETS_BACKEND=aws-secrets-manager` is set in the process env. Requires
  `boto3` installed (this component does not declare it as a hard dependency
  — see "The AWS Secrets Manager path") and an IAM identity with
  `secretsmanager:GetSecretValue` scoped to the secret(s) this app reads
  (least privilege, per `references/security/secure-baseline.md`).

**EXPOSES**
- `get_secret(name, *, required=True, default=None, client=None) -> str | None`
  — the one accessor every consumer imports instead of calling
  `os.environ.get()` directly. `client` is a test-only injection point.
- `validate_required(names: Iterable[str]) -> None` — call once at app
  startup with every secret name the app needs; raises `MissingSecretsError`
  listing every missing name at once if any are unresolved, so a
  misconfigured environment fails loudly before serving a single request.
- `SecretNotFoundError`, `MissingSecretsError`, `SecretShapeError` — the
  three exception types; all carry only the secret's **name**, never a
  value, in their message. `SecretShapeError` is raised (not caught
  internally) when the ASM layer resolves a value that decodes as a JSON
  object with no top-level key matching the requested name — see "The AWS
  Secrets Manager path".
- Its co-located doc fragment: `docs/fragment.md`.

## Why no `.env` parsing

This module deliberately does not read or parse `.env` files itself. The
process env is the interface (12-factor) — a project's chosen framework
already owns `.env` loading for local dev (`pydantic-settings`,
`python-dotenv`, Next.js's built-in loader — see
`references/security/secrets-management.md`'s "Local dev reads `.env` via the
framework's standard loader — no bespoke secret-loading code per block"). A
second, competing `.env` parser inside this module would either duplicate
that loader's precedence rules and quoting behavior badly, or silently
diverge from them. By the time `get_secret()` runs, whatever already loaded
`.env` into `os.environ` has already run — this module only ever reads the
result.

## Layered resolution

`get_secret(name)` checks, in order:
1. `os.environ[name]` — an empty string is treated as unset, not as a
   resolved value (a common misconfiguration, e.g. `FOO=` in a shell env
   file).
2. If `SECRETS_BACKEND=aws-secrets-manager`, AWS Secrets Manager, prefixed by
   `AWS_SECRETS_MANAGER_PREFIX` if set. A structured JSON secret (e.g. a
   `{"DB_PASSWORD": "...", "DB_USER": "..."}` blob) resolves the matching
   top-level key by name; a scalar secret resolves as-is; a JSON object with
   **no** top-level key matching `name` raises `SecretShapeError` instead of
   silently returning the raw multi-field blob as if it were the single
   requested value (see "The AWS Secrets Manager path").
3. `default`, if one was passed.
4. Otherwise: `None` if `required=False`, or a raised `SecretNotFoundError` if
   `required=True` (the default).

Env always wins when present — Secrets Manager is a fallback, never a first
choice, so local dev never makes a network call by accident.

## The AWS Secrets Manager path

`boto3` is imported **lazily**, inside `_get_asm_client()`, and only reached
when `SECRETS_BACKEND=aws-secrets-manager` is actually configured — this
component has no hard `boto3` dependency. A project that never sets that
backend (the common case: local dev, most CI, and any prod that just injects
env vars at container start) never needs `boto3` installed at all. A project
that does enable the ASM backend adds `boto3` itself (`uv add boto3`); if
it's missing, `get_secret()` raises a clear `RuntimeError` naming the fix
instead of a bare `ImportError` traceback.

**A lookup failure logs the exception's TYPE, never its message.** boto3
raises its own generated `ClientError` subclasses
(`AccessDeniedException`, `ResourceNotFoundException`, ...) that this
module has no compile-time dependency on. On any exception from
`get_secret_value()`, the warning log line includes the error's **type
name** — cheaply read off a real `ClientError`'s own
`.response["Error"]["Code"]` shape when present, or the exception's plain
class name otherwise (no botocore import needed either way) — but never
the exception's `str()`/message, which on a path an attacker-shaped
`secret_id` could influence might echo more than intended. This is what
lets an operator tell an IAM misconfiguration (`AccessDeniedException`)
apart from a genuinely missing secret (`ResourceNotFoundException`) from
the log line alone.

**A JSON-object secret with no matching top-level key raises, it doesn't
return the raw blob.** ASM sometimes stores a structured credential (DB
user+password+host) as one JSON blob under a single secret name. If that
JSON decodes as an object and has a top-level key matching the requested
`name`, that field's value is returned. If it decodes as an object but has
**no** matching key, this is a shape mismatch between what's stored and
what's requested — `SecretShapeError` is raised rather than silently
handing back the raw multi-field JSON string as if it were the single
value the caller asked for (an earlier version of this module did exactly
that, and a caller treating the returned "secret" as a password/token
would have gotten a JSON blob instead — see "Judgment calls").

## Never logs values

Every log line and every exception message in this module carries the
secret's **name** only. `get_secret()` logs at `DEBUG` when resolving and at
`ERROR` only on a required-and-missing outcome (by then there is no value to
log — the whole point). This is the mechanism behind
`references/security/secure-baseline.md`'s audit-logging rule: "Logs never
contain secrets, tokens, passwords... Log the fact and the identifiers, not
the sensitive content."

## Testing

`tests/test_secret_store.py` covers: env resolution, the empty-string-is-unset
rule, `validate_required()`'s fail-fast behavior (including listing *every*
missing name, not just the first), that a successful resolution's log output
never contains the resolved value, the AWS Secrets Manager fallback path
(via a hand-written fake client — no `boto3` dependency needed), layering
priority (env beats ASM), the JSON-blob key-extraction case, the JSON-blob
shape-mismatch case raising `SecretShapeError` without ever logging the
blob's other field values, a lookup failure logging a stubbed
`ClientError`'s error code (`AccessDeniedException` vs
`ResourceNotFoundException`, distinguishable from each other) or falling
back to the raw exception type name (`KeyError`) when no ClientError shape
is present — in every case without ever logging the exception's own
message — and the lazy `boto3` import path itself (a fake `boto3` module
planted in `sys.modules`, confirming `_get_asm_client()` reaches
`boto3.client("secretsmanager", ...)` correctly without a real `boto3`
installed).

Run: `uv run --python 3.13 --with pydantic --with pytest -- pytest templates/components/security/secrets-loading/tests/ -q`
(`pydantic` isn't imported by this module; the `--with` list matches the
firm-wide verification invocation used across the three Step 2 components).

## Judgment calls

- **Renamed `secrets.py` → `secret_store.py`.** The original name shadowed
  the stdlib `secrets` module once this component's directory landed on
  `sys.path` (as the tests' `conftest.py` does, and as a scaffolded
  project's own import path would once copied to
  `app/core/security/secrets.py`). That shadow was flagged rather than
  fixed in the original build; a review finding (M5) judged that with
  Stages 3-4 about to hard-code `from app.core.security.<name> import ...`
  across the generated backend, the shadow is pure downside with zero
  compensating benefit (this module provides no stdlib-`secrets`
  functionality — no token/password generation) and should be fixed before
  that hard-coding happens rather than after. Renamed rather than left
  flagged.
- **Empty string treated as unset.** `os.environ.get(name)` returning `""` is
  common for an accidentally-blank `.env`/CI variable; treating it as
  "unset" rather than "resolved to an empty secret" was judged the safer
  default — a truly-intended empty secret is vanishingly rare and can still
  go through `default=""`.
- **`SecretShapeError` is not caught by `validate_required()`.** That
  function only catches `SecretNotFoundError` (the "missing" outcome) and
  lets `SecretShapeError` (a configuration/shape error, a different failure
  mode) propagate uncaught — both still fail app startup loudly, but as
  distinguishable exception types rather than folded into one.
