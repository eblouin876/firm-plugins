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
- Composition contract
- <the granular sections for this block>

## Composition contract

Every template block declares what it **needs** from the rest of the monorepo to run, and what it **exposes** for other blocks and recipes to consume. This is how independently-authored blocks stitch together into one working project without each one knowing the others' internals. Hardened in Stage 1 (#24): the loose "v0" contract from Stage 0 is now pinned to concrete interfaces, now that the monorepo skeleton, the shared `api-client` package, and the doc-fragment aggregation mechanics all exist to pin against.

What's locked (epic #22, hardened Stage 1 #24) that every block's contract is grounded in:
- **pnpm workspaces** — the monorepo is one pnpm workspace; a block that ships JS/TS is a workspace package, discovered via the `apps/*` / `packages/*` globs in `pnpm-workspace.yaml`.
- **The shared, generated `api-client`** — `@repo/api-client`, a typed React Query client generated from the backend's OpenAPI schema (`just client-generate`). A frontend/mobile block *needs* it and configures it once at startup via `configureApiClient({ baseUrl })`, sourcing `baseUrl` from its own framework-prefixed env var (`VITE_API_BASE_URL` / `NEXT_PUBLIC_API_BASE_URL` / `EXPO_PUBLIC_API_BASE_URL` — one mapping per consuming stack, not a single shared var name). A backend block *exposes* the OpenAPI contract `@repo/api-client` is generated from. See `templates/packages/api-client/README.md` for the full interface.
- **A standardized `justfile`** — every block that has runnable behavior wires into the project-root `justfile`'s standard targets: `test`, `lint`, `dev`, `build`, `deploy`, `docs-generate`, `docs-check` (dash-named — `just` forbids `:` in a recipe name; see `references/authoring/documentation-standard.md`). A block doesn't invent its own task-runner surface. `docs-generate`/`docs-check` are live as of Stage 1 (#24, `scripts/docs-aggregate.mjs`); `deploy` stays unwired until an infra/devops block lands (Stage 9) but fails loudly (`exit 1`) rather than silently no-opping.
- **Every block ships a co-located doc fragment** — `docs/fragment.md` inside the block's own materialized directory (e.g. `apps/backend/docs/fragment.md`, `packages/api-client/docs/fragment.md`), in the exact format `references/authoring/documentation-standard.md`'s "Doc fragment format (canonical spec)" defines: a `<!-- fragment: block:<layer>/<name> -->` header line, then optional `## Setup` / `## Deployment` / `## Maintenance` / `## Secrets` sections that `just docs-generate` aggregates into the root README. This is an acceptance bar, not optional polish.

Per-stack directory conventions (exact env var names beyond the `api-client` mapping above, a backend block's internal module layout, a frontend block's routing/state conventions, etc.) are deliberately still **not** pinned here — those harden in the stack-specific stages that compose blocks into this contract (Stages 3-9), each grounded in whatever that stack's own template block README declares.

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
- **Its co-located doc fragment** — `docs/fragment.md`; see below. This is how the block's setup steps, deploy notes, maintenance notes, and secrets reach the project root README.

## Documentation

Every block ships a `docs/fragment.md` co-located with its code that `just docs-generate` aggregates into the project's root README (Setup / Deployment / Maintenance / Secrets — Structure is written directly, not aggregated). This template does not restate that model — see `${CLAUDE_PLUGIN_ROOT}/references/authoring/documentation-standard.md` for the doc-fragment format and the root README template it feeds.

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
