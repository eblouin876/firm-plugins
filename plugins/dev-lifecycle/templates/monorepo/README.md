<!--
block: monorepo                     # root skeleton, not an app-layer <layer>/<name> block or a catalog component
needs:
  - toolchain: Node.js, pnpm, just — pinned ranges per compatibility-matrix.md
exposes:
  - pnpm workspace: apps/* + packages/* — see "Needs/exposes" below
  - justfile surface, shared root config, its co-located doc fragment (this file)
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# Monorepo skeleton

The project-root scaffold every scaffolded project starts from: an empty pnpm
workspace (`apps/*`, `packages/*`) with a standard `justfile` task surface and
shared root tooling config, but no app code yet — that arrives as template
blocks (`backend/*`, `frontend/*`, `mobile/*`, `infra/*`) and catalog
components (e.g. `packages/api-client`) are composed in on top of it. Lives at
`templates/monorepo/` in this repo; `scaffolding` materializes its contents to
a new project's root.

## Needs/exposes
**Needs:** Node.js, pnpm, and `just`, at the ranges pinned in `.nvmrc` /
`package.json`'s `engines` and `compatibility-matrix.md`.

**Exposes:**
- **pnpm workspace** — `apps/*` + `packages/*` (`pnpm-workspace.yaml`), the
  placement every other block/component lands into.
- **`justfile` surface** — the standard dash-named targets (`test`, `lint`,
  `dev`, `build`, `deploy`, `docs-generate`, `docs-check`, `install`,
  `typecheck`) every block wires into rather than inventing its own task
  runner, plus the `client-generate` wiring point that regenerates
  `packages/api-client` once a backend block lands (Stage 3). `docs-generate`
  / `docs-check` are wired as of Stage 1 Step 4 to `scripts/docs-aggregate.mjs`
  (this directory's `scripts/`), which aggregates every composed block's
  `docs/fragment.md` into the root README's marker regions — see
  `references/authoring/documentation-standard.md`. `deploy` stays unwired
  until an infra/devops block lands (Stage 9), but fails loudly (`exit 1`)
  rather than silently no-opping.
- **Shared root config** — `eslint.config.mjs`, `tsconfig.base.json`,
  `.prettierrc`, `.editorconfig`, `.gitignore`/`.dockerignore`,
  `.env.example` — every block extends these rather than redefining them.
- **Its co-located doc fragment** — this file.

## What materializes vs. what's canon
Two payload files here carry the `.tmpl` suffix and are not this repo's own
docs — they are the *content* a scaffolded project ships as its own root
`README.md` and `CLAUDE.md` once scaffolding strips the suffix:
- `README.md.tmpl` — the scaffolded project's root README (Setup / Deployment
  / Maintenance / Secrets / Structure), with the doc-fragment aggregation
  regions Step 4's `docs-generate` script fills in as blocks are composed.
- `CLAUDE.md.tmpl` — the scaffolded project's root `CLAUDE.md`, including the
  "keep the README current" discipline.

Both bodies are canonically defined in
`references/authoring/documentation-standard.md`; these `.tmpl` files are the
materialized copy scaffolding actually consumes, kept in sync with that
document by hand. The `.tmpl` suffix does double duty: this plugin's
header-lint (`scripts/validate_plugin.py`) skips non-`.md` files, so these
payload bodies (which describe the *scaffolded project*, not this plugin) are
exempt from the `last-verified` header this file itself carries; and a
`.tmpl` file is never mistaken for a real `CLAUDE.md`/`README.md` and
auto-loaded into a session working in `firm-plugins` itself. Every other file
in this directory (`justfile`, `package.json`, `pnpm-workspace.yaml`,
`tsconfig.base.json`, `eslint.config.mjs`, `scripts/docs-aggregate.mjs`,
dotfiles) is plugin canon copied verbatim — no `.tmpl` suffix, because
scaffolding materializes those as-is with no placeholder substitution.

## How scaffolding uses it
`scaffolding` copies this whole directory into the new project's root, strips
the `.tmpl` suffix from the two payload files (substituting placeholders like
`<project-name>` along the way), then composes in whichever template blocks
and catalog components the project needs. Each one wires into the `justfile`
targets already defined here rather than inventing its own task surface, and
contributes its own doc fragment for the next `docs-generate` run to fold into
the materialized root README.
