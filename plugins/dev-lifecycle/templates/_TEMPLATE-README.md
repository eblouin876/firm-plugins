<!--
block: <name>                       # e.g. backend/fastapi, frontend/vite-spa, mobile/expo
needs:                              # what this block requires from the monorepo to run (see contract below)
  - <dimension>: <short description>
exposes:                            # what this block provides to the rest of the monorepo
  - <dimension>: <short description>
versions-pinned-to: references/compatibility-matrix.md   # the pinned version set this block was built against
last-verified: <YYYY-MM-DD>         # date this block was last checked against the pinned versions + its own doc fragment
provenance: manual                  # manual | auto-generated (append "(pending review)" until reviewed)
# note: blocks intentionally omit `sources:` — a block cites its versions via its
# compatibility-matrix entry (versions-pinned-to), not an inline sources list.
-->

# <Block name> template

One or two sentences on what this block is and where it sits in the monorepo (`templates/<layer>/<name>/`). Everything here is **subordinate to the project's existing conventions** — when a scaffolded project has already diverged, the project wins.

## Contents
- Composition contract (v0)
- <the granular sections for this block>

## Composition contract (v0)

Every template block declares what it **needs** from the rest of the monorepo to run, and what it **exposes** for other blocks and recipes to consume. This is how independently-authored blocks stitch together into one working project without each one knowing the others' internals. "v0" because the contract is intentionally loose at Stage 0 — it hardens into concrete schemas/interfaces in Stage 1 (#24), once the monorepo skeleton and shared `api-client` package exist to pin against.

What's already locked (epic #22) that every block's contract is grounded in:
- **pnpm workspaces** — the monorepo is one pnpm workspace; a block that ships JS/TS is a workspace package.
- **A shared, generated `api-client`** — web and mobile consume one typed client generated from the backend's OpenAPI schema. A frontend/mobile block *needs* it; a backend block *exposes* the OpenAPI contract it's generated from.
- **A standardized `justfile`** — every block that has runnable behavior wires into the project-root `justfile`'s standard targets: `test`, `lint`, `dev`, `build`, `deploy`, `docs:generate`, `docs:check`. A block doesn't invent its own task-runner surface.
- **Every block ships a co-located doc** — see `references/authoring/documentation-standard.md` (below). This is an acceptance bar, not optional polish.

Do not over-specify beyond this: exact env var names, the generated client's interface, and per-stack directory conventions are deliberately undecided here and get hardened in Stage 1 (#24) and the stack-specific stages that follow it.

### NEEDS
What a block requires to function, so the monorepo can supply it before the block is wired in:
- **Env vars** — the variables the block reads at runtime (names/shapes finalized per-block; declare them here once known).
- **Backing services** — e.g. a Postgres database, Redis, an object store.
- **Ports** — what the block listens on / expects to reach.
- **Upstream API contract** — if the block is a consumer (frontend, mobile), which backend contract it expects (the generated `api-client`, or a specific OpenAPI surface).
- **Shared workspace packages** — other pnpm workspace packages it imports (e.g. `packages/api-client`).

### EXPOSES
What a block provides, so other blocks/recipes can depend on it:
- **Routes + OpenAPI** — if the block is a backend, the routes it serves and the OpenAPI schema it generates.
- **Env it provides** — any env vars/config the block publishes for consumers (e.g. a base URL).
- **Workspace packages it publishes** — e.g. a backend block publishing the OpenAPI spec that `packages/api-client` generates from.
- **Ports** — what the block serves on.
- **Its co-located doc fragment** — see below; this is how the block's README section, deploy notes, and secrets reach the project root README.

## Documentation

Every block ships a doc fragment co-located with its code that aggregates into the project's root README (Setup / Deployment / Maintenance / Secrets / Structure). This template does not restate that model — see `${CLAUDE_PLUGIN_ROOT}/references/authoring/documentation-standard.md` for the doc-fragment format and the root README template it feeds.

## <Sections>
Granular block-specific guidance goes here when this template is used to author a real block (Stage 1 onward): what it scaffolds, its directory layout, and how it wires into the `justfile` targets.

---
<!--
Authoring rules for a template block README:
- Fill in `needs` / `exposes` concretely once the block's actual contract is known; don't leave placeholders in a shipped block.
- `versions-pinned-to` must point at the compatibility matrix entry that governs this block's stack.
- Ship the co-located doc fragment alongside this file — "ships its doc" is an acceptance bar the `template-author` skill enforces.
- Update `last-verified` whenever the block or its pinned versions change.
- This file (`_TEMPLATE-README.md`) is `_`-prefixed and skipped by header lint — it's the schema exemplar, not a real block. Real blocks use this filename without the underscore, at `templates/<layer>/<name>/README.md`.
-->
