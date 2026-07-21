# 0001. Templates, recipes, a monorepo golden path, and standardized security/docs

## Status
Accepted

## Context
Before Stage 0 (epic #22, issue #23), the plugin gave a build session two things: a library of per-library **references** (idiom/version guidance a skill loads when it meets a framework) and **model-driven scaffolding** that stood up a repo's structure and pipeline from a plan. What it did not give a project was anything *runnable* — no golden-path starter code, no opinionated way to compose a backend/frontend/mobile/infra stack into one working monorepo, no standard for how a project's security defaults should look out of the box, and no standard for how a project's own documentation should stay true to its code as it grows. Each scaffolded project reinvented these, inconsistently, every time.

## Decision
Introduce four new artifact types and one cross-cutting standard into the plugin, all under the existing self-extending-library model (metadata headers, `last-verified`, PR-gated changes):

- **(a) Templates as a new artifact type** — composable golden-path **blocks** (`templates/<layer>/<name>/`, e.g. `backend/fastapi`) plus a **catalog of components** (`templates/components/<domain>/`, lighter drop-in slices and shared packages like the generated `api-client`). Each declares a composition contract (`needs`/`exposes`) so independently-authored blocks stitch together without knowing each other's internals. Authored via the new `template-author` skill.
- **(b) Feature recipes** — portable how-tos (`references/recipes/<name>.md`) that wire an existing block/component into a concrete feature (Stripe checkout, S3 uploads, an auth provider) without inventing new infrastructure. Authored via the new `recipe-author` skill.
- **(c) The monorepo golden path** — pnpm workspaces as the one workspace every JS/TS block joins; a shared, generated `api-client` package (from the backend's OpenAPI schema) that web and mobile blocks consume; and a standardized project-root `justfile` with the fixed target surface (`test`, `lint`, `dev`, `build`, `deploy`, `docs:generate`, `docs:check`) every runnable block wires into instead of inventing its own task runner.
- **(d) A standardized security baseline** (`references/security/secure-baseline.md`, plus `attack-surfaces.md`, `secrets-management.md`, `payments-security.md`, `data-protection.md`) every block and recipe inherits by default — anchored to OWASP Top 10:2025 / ASVS 5.0 — so "secure-by-default" is a bar authoring enforces, not a checklist a scaffolded project has to remember.
- **(e) Documentation-as-source-of-truth** (`references/authoring/documentation-standard.md`) — every block, component, and recipe ships a portable doc fragment co-located with its own code; fragments aggregate into the scaffolded project's root README (Setup / Deployment / Maintenance / Secrets / Structure) and are pointed to by a project `CLAUDE.md`, rather than a hand-maintained doc drifting from the code it describes.

A pinned, kit-wide **compatibility matrix** (`references/compatibility-matrix.md`) underlies (a)-(c): a block does not choose its own version of a kit-wide dependency, it pins to the matrix, and the matrix wins on disagreement.

## Consequences
- Every template block and catalog component must clear **four acceptance bars** before it ships, no exceptions: composition-contract present, documented (ships its doc fragment), version-pinned (to the compatibility matrix), and secure-by-default (meets the secure baseline). `template-author` enforces this at authoring time; a block missing any bar is not done even if its code runs.
- A feature recipe clears the same documented / version-pinned / secure-by-default bars wherever it touches those surfaces, enforced by `recipe-author`; it does not carry a full composition contract since it isn't itself a block.
- Every per-stack block's `versions-pinned-to` is grounded in the compatibility matrix, not chosen independently — bumping a matrix line is a deliberate, matrix-wide change (re-verify against official sources, update `last-verified`), not a per-block decision.
- The plugin's existing weekly **freshness audit** extends its remit from references alone to templates, components, recipes, and their doc fragments — staleness in the starter kit is now caught the same way staleness in a reference is.
- The composition contract is intentionally "v0" at this stage: exact env var names, the generated `api-client`'s interface, and per-stack directory conventions are deliberately left open here and harden in Stage 1 (#24) once the monorepo skeleton and shared `api-client` package actually exist to pin against. Authors must not over-specify past what Stage 0 has locked.
- This decision is scoped to Stage 0 of epic #22 (plugin expansion) — it establishes the conventions and skills; it does not yet materialize the monorepo skeleton, a first real block, or the aggregation mechanics behind `docs:generate`/`docs:check`. Those are later stages of the same epic and will reference this ADR rather than relitigate it.
