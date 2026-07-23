<!--
recipe: feature-flags
applies-to:
  - backend block: fastapi OR django (env/DB-backed evaluation; framework-neutral pattern)
  - frontend block: any React web block (flag value passed down from the backend, or read from the same env source at build time for a static toggle)
last-verified: 2026-07-23
provenance: manual
sources:
  - references/backend/pydantic.md
  - templates/components/backend/settings/settings.py
  - references/security/secure-baseline.md
-->

# Feature flags

Wire flag evaluation to gate an endpoint or a UI surface, kept deliberately simple and dependency-light: env-backed flags via the settings component for a small, deploy-time-toggleable set, a DB-backed table for flags that need to change without a redeploy, and a **default-off, kill-switch** posture throughout. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps (env-backed flags — the default)
- Wire-up steps (DB-backed flags — when env isn't enough)
- Gating an endpoint vs. gating UI
- Default-off and the kill-switch posture
- What the kit does not provide (a flag provider/SDK)
- Doc fragment

## What this wires
Applying this recipe gives a feature a boolean (or small enum) toggle a project can flip without shipping new code for the toggle itself: a new, half-finished, or risky feature ships disabled by default, is enabled by config once ready, and can be flipped back off immediately (a kill switch) if it misbehaves in production — all without a deploy in the enable/disable path itself once the flag mechanism is wired.

It **composes existing pieces** — it invents no new infrastructure and pulls in no third-party flag provider:
- **`templates/components/backend/settings/settings.py`** — the `AppSettings` pydantic-settings base every backend block already has; the simplest, most kit-idiomatic flag is just another field on it (`FEATURE_NEW_CHECKOUT: bool = False`), following the same fail-fast-at-startup, env/`.env`-sourced pattern every other config value already uses. No new loading mechanism to build.
- **`references/backend/pydantic.md`**'s "Settings & secrets" convention — configuration (which a feature flag fundamentally is) comes from `pydantic-settings`, not a hardcoded constant or an ad hoc `os.environ.get` scattered through the codebase.
- **`references/security/secure-baseline.md`**'s least-privilege posture, applied to flags: a flag gating access to unfinished or admin-only functionality is itself an authorization-adjacent control — see "Default-off and the kill-switch posture" below for how that interacts with `require_roles` from the auth component.

## Prerequisites
- A backend block with `AppSettings` (the `settings` catalog component) vendored — ships by default in every backend block.
- For DB-backed flags specifically: a simple `feature_flags` table (or reuse of an existing project-wide key/value config table if one exists) and, if flags must be toggleable without a deploy, an admin-only route or Django admin registration to flip them — gated by the existing `require_roles`/admin RBAC the `end-to-end-auth` recipe already wires, not a new auth mechanism.
- No compatibility-matrix row and no new dependency for the default (env-backed) path — it's a `bool` field on an existing Pydantic settings class.

## Wire-up steps (env-backed flags — the default)
Start here. Most flags in a small-to-medium project are this simple, and env-backed is the kit-idiomatic default — reach for the DB-backed path (below) only when a flag genuinely needs to change without a redeploy or needs to vary per-user/per-tenant.

1. **Add the flag as a field on the project's `Settings` subclass** (the one that already extends `AppSettings`), following the same naming and default posture every other config field uses:
   ```python
   class Settings(AppSettings):
       feature_new_checkout: bool = False   # default OFF — see "Default-off" below
   ```
   `pydantic-settings` resolves it from the environment (`FEATURE_NEW_CHECKOUT=true`) the same way every other field is resolved — no new loading code.
2. **Read the flag from the settings instance at the call site that needs it** — a route dependency, a service method, a template context processor (Django) — never re-read `os.environ` directly at the point of use; go through the one `Settings` instance the app already constructs once at startup, same as every other config value.
3. **A flag that changes behavior in a way a client needs to know about (to show/hide UI) is exposed through an existing authenticated route**, not a new unauthenticated `/flags` endpoint that leaks the project's full flag inventory to anyone — see "Gating an endpoint vs. gating UI" below.

## Wire-up steps (DB-backed flags — when env isn't enough)
Reach for this only when a flag needs one or more of: toggling without a redeploy, a per-tenant/per-user value, or a non-technical operator flipping it through an admin UI. It is meaningfully more machinery than the env-backed path — don't default to it.

1. **Model a minimal table**: `key` (unique string), `enabled` (bool, default `False`), optionally `rollout_percent`/`enabled_for_user_ids` if the project genuinely needs partial rollout (keep this minimal — a full percentage-rollout/targeting engine is a "graduate to a real provider" signal, see "What the kit does not provide"). Use the same `db-mixins`/`repository` catalog components every other model in the kit already uses — no bespoke persistence layer for flags specifically.
2. **Cache the read, don't hit the DB on every request.** A flag check that runs a query on every request to every gated route is a needless hot-path cost for a value that changes rarely — apply the `caching` recipe's cache-aside pattern with a **short** TTL (seconds, tens of seconds) so a flag flip propagates quickly without every read being a DB round trip. This is the one place this recipe composes with another recipe rather than a catalog component directly.
3. **Gate the write path (flipping a flag) behind the same admin RBAC** the `end-to-end-auth` recipe's `require_roles("admin")` example already demonstrates — flag state is operationally sensitive (it can gate a payment flow, an auth change, anything), never expose an unauthenticated or non-admin-writable toggle endpoint.
4. **Audit flag changes** via the `audit-logging` recipe's `audit_event(...)` — `audit_event("feature_flag.toggle", actor=admin_user_id, resource=f"flag:{key}", outcome="success", enabled=new_value)` — a flag flip is exactly the kind of admin action that recipe's "What to audit" section already names.

## Gating an endpoint vs. gating UI
- **Endpoint gating** (the authoritative check): the backend route itself checks the flag before executing the gated logic and returns `404`(hides the feature's existence entirely) or `403`(the feature exists but isn't enabled for this caller) as appropriate — **never trust a client-side-only check** for anything the backend must actually enforce. A flag that only hides a button in the UI while the underlying endpoint still executes for anyone who calls it directly is not gated at all.
- **UI gating** (the presentation layer): the frontend reads the flag's *value* — passed down via an authenticated `/me`-style response, a dedicated `/config` response scoped to the authenticated caller, or (for a purely cosmetic, non-security-relevant toggle only) a build-time env var baked into the frontend bundle — and conditionally renders. UI gating is a UX nicety layered on top of endpoint gating, never a substitute for it.
- **Don't ship a flag's raw value to an unauthenticated client** if the flag itself reveals something sensitive about the system (an internal migration in progress, an unreleased feature name) — scope what's exposed to what that caller is allowed to know, the same discipline `references/security/data-protection.md` already applies to any other response field.

## Default-off and the kill-switch posture
- **Every new flag defaults to `False` (or its off/safe state)** — a flag that defaults on the moment it's added isn't a flag, it's just the new behavior with extra config surface. The safe, well-understood behavior is always what happens with no configuration present.
- **A flag is a kill switch, not just a launch switch** — design the gated code path so flipping the flag back to `False` in production genuinely reverts to the prior working behavior, not to an error state. If flipping a flag off would itself break something, that flag has failed at its actual job.
- **Keep the flag list small and time-bounded.** A flag that's been `True` in every environment for months with no plan to remove the gate is dead weight — the gated branch and the flag both stay as permanent complexity for no ongoing benefit. Remove the flag (and the old code path) once a feature is fully rolled out and stable, rather than letting it accumulate.

## What the kit does not provide (a flag provider/SDK)
This recipe deliberately stays dependency-light: no LaunchDarkly/Unleash/Flagsmith SDK, no separate flag-evaluation service, no percentage-rollout/targeting engine. That is a **conscious kit-scope decision**, not an oversight, and it is the right call for most projects at this kit's target scale — but it stops being enough the moment a project genuinely needs: real percentage-based rollout with consistent bucketing, fine-grained per-attribute targeting rules, a non-engineer-facing flag-management UI, or flag evaluation shared consistently across several independent services. At that point, adopting a real flag provider is a deliberate, reviewed **project-level decision** (a new dependency, a new external service, a new compatibility-matrix row) — not something this recipe's env/DB-backed pattern should be stretched to fake. Don't cite a flag-provider SDK as something this kit wires; it doesn't.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Feature flags
- **Setup:** Simple flags are fields on the project's `Settings` (pydantic-settings) — `FEATURE_<NAME>=true` in the environment, default `False`. Flags that must change without a redeploy live in a small DB table instead, cached with a short TTL, writable only by an admin-gated route (audited via `audit_event(...)`). The backend endpoint itself is the authoritative gate (404/403 as appropriate) — UI-only hiding is never a substitute.
- **Secrets:** none — flag values aren't secrets, though a flag name can be operationally sensitive (avoid exposing the full flag inventory to unauthenticated clients).
- **Maintenance:** New flags default off. Remove a flag (and its gated branch) once a feature is fully rolled out — don't let flags accumulate indefinitely. Reach for a real flag provider only when rollout/targeting needs genuinely outgrow env/DB-backed evaluation; the kit ships no SDK for one today.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2).
Wires the existing settings/AppSettings catalog component for the default
env-backed path; the DB-backed path composes the existing db-mixins/
repository components plus the caching and audit-logging recipes rather
than inventing new persistence or caching machinery. Explicitly states the
kit ships no flag-provider SDK — a deliberate scope decision, not a gap to
paper over with a fake component citation.
-->
