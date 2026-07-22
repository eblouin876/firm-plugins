<!--
scope: documentation-standard        # cross-cutting canon, not a single library — see references/_TEMPLATE.md for the library-doc header this variant replaces
last-verified: 2026-07-22
provenance: manual
sources: []
-->

# Documentation standard: co-located docs, aggregated to the root README

How a starter-kit project's documentation stays true to the code as blocks, components, and recipes are composed into it. Read by the `template-author` and `recipe-author` skills when authoring a new artifact, and by the `documentation` skill when writing or maintaining project docs. Subordinate to a project's existing conventions where one already exists.

## Contents
- The portable, co-located doc model
- The root README template (canonical source)
- Aggregation markers (canonical spec)
- Doc fragment format (canonical spec)
- The project CLAUDE.md template (canonical source)
- "Ships its doc" is an acceptance bar

## The portable, co-located doc model

Docs that live far from the code they describe go stale; docs generated once and never touched again go stale faster. So every template block, catalog component, and feature recipe ships a **doc fragment** co-located with its own files (its `docs/fragment.md` once materialized into a project — see "Doc fragment format" below — or the `## Doc fragment` section of a recipe) rather than a separate, hand-maintained project doc.

- The fragment is **portable**: plain markdown, no dependency on where it ends up, written to slot into a larger document unchanged.
- The fragment **travels with the code**: when a block or recipe is added to (or removed from) a project, its fragment comes with it.
- Fragments **aggregate into the project's root README** — the single source of truth a developer reads first. The root README does not restate each block's internals; it collects what each block/component/recipe already declared about itself: how to set it up, deploy it, maintain it, and where its secrets come from.
- This composes with the `template-author` composition contract (`templates/_TEMPLATE-README.md`): a block's `exposes` list includes its doc fragment as a first-class thing it provides, alongside routes and packages.

Stage 1 (#24) materializes the aggregation mechanics (how fragments actually get pulled into the root README, and the `justfile`'s `docs-generate` / `docs-check` targets that keep them honest). This document defines the model and the canonical template bodies those mechanics assemble from.

**Naming convention:** `just` (stable, 1.21.x) does not allow `:` in a recipe or alias name — it's reserved as the dependency separator — so every `justfile` target in this standard and its templates is **dash-named** (`docs-generate`, `docs-check`, `client-generate`), never colon-named. This applies only to `just` targets; pnpm **script** names (in a `package.json`) may still use colons where that's the natural convention — none of this kit's shipped `package.json`s currently do, but nothing here forbids it.

**Payload vs. canon convention:** a template body in this document that materializes into a *scaffolded project's own files* (rather than staying plugin canon) ships from its `templates/` location with a `.md.tmpl` suffix (e.g. `templates/monorepo/README.md.tmpl`). Scaffolding strips the suffix when it copies the file into the new project. The suffix does two jobs: this plugin's header-lint (`scripts/validate_plugin.py`) only checks bare `*.md` files, so a payload body describing the *scaffolded project* (not this plugin) isn't held to this plugin's own doc-header bar; and a `.tmpl` file is never mistaken for a real `CLAUDE.md`/`README.md` and auto-loaded into a session working in `firm-plugins` itself. A block's or component's **own** doc fragment (its co-located `README.md`) is not a payload template — it's real canon describing that block, ships as bare `.md`, and carries the `last-verified` header like any other reference.

## The root README template (canonical source)

This is the canonical section set every scaffolded project's root README is built from. Stage 1 (#24) materializes this body at `templates/monorepo/README.md.tmpl` for scaffolding to consume via `${CLAUDE_PLUGIN_ROOT}` (stripping the `.tmpl` suffix on materialization); this document remains the source of truth those two stay in sync with. The payload is not a byte-for-byte copy of the body below: it additionally wraps the Setup/Deployment/Maintenance/Secrets sections in the aggregation marker regions defined next, and it drops the illustrative `<ENV_VAR>` Secrets example row shown here (a real project's Secrets rows come only from composed blocks' fragments). Canon remains the source of truth for the section set and body wording; the payload materializes that wording plus the aggregation mechanics.

```markdown
# <project-name>

One-line description of what this project is and who it's for.

## Setup
Prerequisites, install, and the shortest path to running the project locally.
Aggregates each block's own setup steps (backend, frontend, mobile, infra) —
right-size to what's actually present in this project.

## Deployment
How the project ships: the pipeline, environments, and how to trigger a deploy.
Aggregates each block's/component's deploy notes (e.g. infra block's Terraform
apply, backend/frontend build+deploy steps).

## Maintenance
Routine upkeep: how dependencies are updated, how the compatibility matrix is
tracked, how the freshness audit surfaces drift, and how to run the standard
`justfile` targets (`test`, `lint`, `dev`, `build`, `deploy`, `docs-generate`,
`docs-check`).

## Secrets
Every secret this project needs, and **where to get each one** — not the
secret values themselves. Aggregates each block's/recipe's secrets subsection
(e.g. a payments recipe's API keys, an infra block's cloud credentials).

| Secret | Used by | Where to get it |
| --- | --- | --- |
| `<ENV_VAR>` | <block/recipe> | <issuer / dashboard / vault path> |

## Structure
A short orientation to the monorepo layout — the workspace packages and
where each block/component lives — so a reader can find their way around
without reading every directory.
```

## Aggregation markers (canonical spec)

This is the canonical spec for the anchor-marker pairs `just docs-generate` uses to write each composed block's doc-fragment contribution into an aggregating section of the root README (Setup, Deployment, Maintenance, Secrets), and to find, replace, or remove that contribution on a later run without disturbing hand-written prose above it or another block's region. `templates/monorepo/README.md.tmpl` materializes this spec; its header comment is a pointer back here, not a second source of truth.

**Marker syntax.** A region is delimited by a pair of HTML comments, each occupying its own line:

```
<!-- BEGIN block:<layer>/<name> -->
<!-- END block:<layer>/<name> -->
```

`<layer>/<name>` matches the block's own placement in the composed project (e.g. `backend/fastapi`, `packages/api-client`), so the generator and a human diff can tell at a glance which block a region came from. Matching is anchored to the full line: a marker comment occupies its own line, and the whole line must match the pattern, not merely contain it. Parsers may normalize internal whitespace when matching, but the emitter always writes the canonical single-space form shown above — one space after `<!--` and before `-->`, one space around `block:<layer>/<name>`.

**Section scoping.** A `<layer>/<name>` marker id is not document-unique. Each of the four aggregating sections (Setup, Deployment, Maintenance, Secrets) gets its own independent BEGIN/END pair per composed block — the same block can contribute up to four regions, one per section it has a fragment for, all sharing the same `<layer>/<name>`. The generator must resolve the enclosing `##` section first, then match markers only within it; it must never dedupe or reorder markers across sections — a `backend/fastapi` region in Setup and a `backend/fastapi` region in Secrets are unrelated for matching purposes.

**Sentinel lifecycle.** The literal id `<layer>/<name>` (used verbatim, not as a placeholder for some real block's name) is reserved as the empty-state sentinel. On a fresh scaffold with no blocks composed in, each aggregating section holds exactly one `<!-- BEGIN block:<layer>/<name> -->` / `<!-- END block:<layer>/<name> -->` pair, showing future block authors and the generator the exact syntax to use. On the first real fill of a section, `just docs-generate` removes the sentinel pair; it is re-created only if every real block is later removed and the section returns to empty. A real block's region must never be named `<layer>/<name>` — that id is permanently reserved for the sentinel.

**Parser guidance.** Match against the full comment line, never a substring search for `block:` — that token also appears in explanatory prose (including in this document and in the payload's own header comment), and a substring match would false-positive on it. Parsers must also be fence-blind: track fenced-code-block state (` ``` `/`~~~`, closing only on a same-or-longer marker of the same character, per CommonMark) and skip every line inside a fence, so a marker-shaped or heading-shaped line quoted inside a code sample is never mistaken for a real one.

**Secrets section specifics.** The `| Secret | Used by | Where to get it |` header row and its `| --- | --- | --- |` separator live outside and above the marker regions, written once by the template itself. A block's Secrets fragment contributes table rows only, inside its own BEGIN/END pair; the generator must not re-emit the header or separator per block.

**Nesting.** Regions never nest. Within a section they are flat siblings, one per contributing block, in whatever order the generator writes them.

**Region ownership.** Everything between a block's BEGIN and END marker is owned by the generator: it is fully regenerated from that block's own doc fragment on every `just docs-generate` run. Never hand-edit content inside a region directly — edit the block's own co-located `README.md` doc fragment instead, then regenerate. A hand-edit inside a region with no fragment behind it is silently overwritten on the next run.

## Doc fragment format (canonical spec)

This is the canonical spec for `docs/fragment.md` — the file a composed block or catalog component ships **co-located inside its own directory in the scaffolded project** (e.g. `apps/backend/docs/fragment.md`, `packages/api-client/docs/fragment.md`), which `just docs-generate` reads as the *input* it aggregates into the marker regions defined above. A block's authoring-time doc (`templates/<layer>/<name>/README.md` in this repo) is prose for a human browsing the template library; `docs/fragment.md` is the narrow, machine-parseable slice of that same information the generator actually consumes once the block is materialized into a project. A block missing its fragment simply contributes nothing — this is not an error (see "Zero-fragment safety" in the generator's own behavior), but it does fail the "ships its doc" acceptance bar below.

**Header line.** The first non-blank line of the file is a full-line HTML comment identifying the block:

```
<!-- fragment: block:<layer>/<name> -->
```

`<layer>/<name>` matches the same id used in the aggregation markers (e.g. `backend/fastapi`, `packages/api-client`) — the generator uses it to know which id to wrap the fragment's contributed regions in. It must appear exactly once, on the first non-blank line; a missing or malformed header is a malformed-input error. The literal id `<layer>/<name>` is reserved for the empty-state sentinel (see "Sentinel lifecycle" above); a real fragment declaring it is malformed input.

**Sections.** After the header, the fragment holds zero or more of the following `##` sections, each at most once, in any order: `## Setup`, `## Deployment`, `## Maintenance`, `## Secrets`. A section absent from the fragment contributes nothing to that README section for this block — the generator does not emit an empty region for it.

- `## Setup`, `## Deployment`, `## Maintenance` — free-form markdown, copied verbatim (minus the `##` heading line itself, and minus leading/trailing blank lines) into the block's BEGIN/END region under the matching root-README section.
- `## Secrets` — table **rows only**, one per secret, `| NAME | used-by | where-to-get |`. No header row and no separator row: the root README's Secrets table header/separator is written once by the template itself (see "Secrets section specifics" above), and each block contributes rows inside its own region beneath it.

Any `##` heading in the fragment other than these four is malformed input — the generator refuses (exit 2) rather than silently dropping or guessing at it. A fragment that repeats the same `##` section twice is likewise malformed.

**Discovery.** `just docs-generate` discovers fragments by looking for `docs/fragment.md` one level under every directory in `apps/*` and `packages/*` at the project root, and processes them in a deterministic sort by block id — so aggregation output never depends on filesystem enumeration order. Two fragments declaring the same block id is a malformed-input error (ambiguous which one owns that id's regions).

## The project CLAUDE.md template (canonical source)

Every scaffolded project also gets a `CLAUDE.md` explaining its structure and behavior — and, critically, the discipline for keeping the README current so it doesn't drift the way hand-maintained docs do. Stage 1 (#24) materializes this body at `templates/monorepo/CLAUDE.md.tmpl` for scaffolding to consume via `${CLAUDE_PLUGIN_ROOT}` (stripping the `.tmpl` suffix on materialization); this document remains the source of truth the two stay in sync with.

```markdown
# CLAUDE.md

Guidance for any Claude instance working in this repository.

## What this project is
One or two sentences: purpose, and the blocks composed into it (backend,
frontend, mobile, infra) per `templates/_TEMPLATE-README.md`'s composition
contract.

## Structure
Pointer to the root README's Structure section — do not duplicate; link to it.

## Keeping the README current
The root README aggregates a doc fragment from every block, component, and
recipe in this project. When you add, remove, or materially change one:
1. Update (or add) that artifact's own co-located doc fragment first —
   it is the source fact.
2. Re-run `just docs-generate` (or the project's equivalent) so the root
   README reflects the change, and `just docs-check` before committing to
   catch drift.
3. Never hand-edit an aggregated section of the root README directly without
   also updating the fragment it came from — the next regeneration will
   silently overwrite a hand-edit that has no fragment behind it.
A stale README is treated as a bug: the `documentation` and `code-review`
skills flag it.
```

## "Ships its doc" is an acceptance bar

A template block, catalog component, or feature recipe is not done when its code works — it is done when its co-located doc fragment exists, is accurate, and is ready to aggregate. The `template-author` and `recipe-author` skills enforce this the same way they enforce the composition contract and the secure-by-default bar: an artifact without its doc fragment does not clear authoring. The `documentation` skill and `code-review` are the backstop for drift after the fact; the weekly freshness audit (Stage 12, #35) covers doc drift across the whole library.
