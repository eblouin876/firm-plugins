---
name: "template-author"
description: "Author a new template block for this plugin's monorepo starter kit — decide its layer and placement under templates/<layer>/<name>/, fill its composition contract (needs/exposes), and clear the four acceptance bars (composition-contract, documented, version-pinned, secure-by-default) before it ships. Use this skill WHENEVER extending the starter kit's catalog: \"add a template block\", \"author a backend/frontend/mobile/infra block\", \"add a component to the catalog\", \"scaffold a new block for the kit\". This is a META-skill invoked by build agents and humans EXTENDING the kit itself — not for building an app feature. For building an app that USES a block, see the relevant build skill (backend, frontend, ...); for wiring an existing block into a feature, see recipe-author."
---

# Template author

A template block is a unit of the starter kit's catalog — a backend, frontend, mobile, or infra piece that scaffolding composes into a project. This skill is the discipline for adding one: where it lives, what it declares about itself, and the four bars it must clear before another block (or a human) can depend on it. It is invoked by build agents and humans who are extending the kit, never by a build agent building an actual app feature — that consumes blocks, it doesn't author them.

## Core rules

- **One block, one directory, one contract.** A block lives at `${CLAUDE_PLUGIN_ROOT}/templates/<layer>/<name>/` and declares its composition contract in its own `README.md` — no implicit coupling to another block's internals.
- **The contract is the interface.** Other blocks and recipes wire against a block's declared `needs`/`exposes`, never against its file layout. Under-declaring breaks composition silently; over-declaring locks in interfaces before Stage 1 (#24) hardens them — state only what's actually true today.
- **All four bars, every block, no exceptions.** A block that's missing its doc fragment, its version pin, or its secure-by-default posture is not done, even if the code runs.
- **Subordinate to the project.** Everything a block does is a default a scaffolded project can and will diverge from — say so in the block's README, don't fight it later.

## Workflow

### 1. Decide the block's layer, name, and placement

Pick the layer (`backend`, `frontend`, `mobile`, `infra`, or a new one if the kit genuinely needs it) and a short, concrete name (e.g. `backend/fastapi`, `frontend/vite-spa`, `mobile/expo`). Place it at `${CLAUDE_PLUGIN_ROOT}/templates/<layer>/<name>/`. Check the catalog first — don't author a near-duplicate of an existing block; extend or parameterize the existing one instead.

### 2. Fill the block header and its composition contract

Copy the structure from `${CLAUDE_PLUGIN_ROOT}/templates/_TEMPLATE-README.md` — the block header (`block`, `needs`, `exposes`, `versions-pinned-to`, `last-verified`, `provenance`) plus the `Composition contract (v0)` section — into the block's own `README.md`, and fill it concretely:

- **NEEDS** — env vars it reads, backing services, ports, upstream API contract (e.g. the generated `api-client`), shared workspace packages it imports. Don't leave placeholders in a shipped block.
- **EXPOSES** — routes/OpenAPI it serves, env/config it publishes, workspace packages it publishes, ports it serves on, and its own doc fragment (below).

Don't over-specify past what's locked at Stage 0 (pnpm workspaces, the shared `api-client`, the standard `justfile` targets) — exact schemas and per-stack conventions hardening happens in Stage 1 (#24) and later stack-specific stages.

### 3. Clear the four acceptance bars

A block does not clear authoring until all four are true, each grounded in the kit's canon:

- **Composition-contract present** — `needs`/`exposes` filled concretely per `${CLAUDE_PLUGIN_ROOT}/templates/_TEMPLATE-README.md`.
- **Documented** — ships a co-located doc fragment that aggregates into the project's root README, per `${CLAUDE_PLUGIN_ROOT}/references/authoring/documentation-standard.md`.
- **Version-pinned** — `versions-pinned-to` points at the governing entry in `${CLAUDE_PLUGIN_ROOT}/references/compatibility-matrix.md`.
- **Secure-by-default** — the block's defaults meet `${CLAUDE_PLUGIN_ROOT}/references/security/secure-baseline.md` out of the box, with no insecure default a scaffolded project has to remember to fix.

### 4. Wire it into the `justfile` targets

If the block has runnable behavior, it wires into the project-root `justfile`'s standard targets (`test`, `lint`, `dev`, `build`, `deploy`, `docs:generate`, `docs:check`) rather than inventing its own task surface.

### 5. Verify and hand off

Run `python scripts/validate_plugin.py` — a real (non-`_`-prefixed) block's `README.md` is checked for a `last-verified` header. Confirm the block builds/runs standalone against its declared `needs`. Hand off by naming the block and layer so `scaffolding` and other authors can pick it up.

## What this skill does NOT do

- Build an app feature — that's the relevant build skill (`backend`, `frontend`, ...) consuming an already-authored block.
- Scaffold a project from the catalog — that's `scaffolding`.
- Ship a block missing any of the four bars, even temporarily.
