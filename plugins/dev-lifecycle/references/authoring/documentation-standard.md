<!--
scope: documentation-standard        # cross-cutting canon, not a single library — see references/_TEMPLATE.md for the library-doc header this variant replaces
last-verified: 2026-07-21
provenance: manual
sources: []
-->

# Documentation standard: co-located docs, aggregated to the root README

How a starter-kit project's documentation stays true to the code as blocks, components, and recipes are composed into it. Read by the `template-author` and `recipe-author` skills when authoring a new artifact, and by the `documentation` skill when writing or maintaining project docs. Subordinate to a project's existing conventions where one already exists.

## Contents
- The portable, co-located doc model
- The root README template (canonical source)
- The project CLAUDE.md template (canonical source)
- "Ships its doc" is an acceptance bar

## The portable, co-located doc model

Docs that live far from the code they describe go stale; docs generated once and never touched again go stale faster. So every template block, catalog component, and feature recipe ships a **doc fragment** co-located with its own files (its `README.md`, or the `## Doc fragment` section of a recipe) rather than a separate, hand-maintained project doc.

- The fragment is **portable**: plain markdown, no dependency on where it ends up, written to slot into a larger document unchanged.
- The fragment **travels with the code**: when a block or recipe is added to (or removed from) a project, its fragment comes with it.
- Fragments **aggregate into the project's root README** — the single source of truth a developer reads first. The root README does not restate each block's internals; it collects what each block/component/recipe already declared about itself: how to set it up, deploy it, maintain it, and where its secrets come from.
- This composes with the `template-author` composition contract (`templates/_TEMPLATE-README.md`): a block's `exposes` list includes its doc fragment as a first-class thing it provides, alongside routes and packages.

Stage 1 (#24) materializes the aggregation mechanics (how fragments actually get pulled into the root README, and the `justfile`'s `docs:generate` / `docs:check` targets that keep them honest). This document defines the model and the canonical template bodies those mechanics assemble from.

## The root README template (canonical source)

This is the canonical section set every scaffolded project's root README is built from. Stage 1 (#24) will materialize this body under `templates/monorepo/README.md` (or equivalent) for scaffolding to consume via `${CLAUDE_PLUGIN_ROOT}`; until then, this is the source of truth an authoring skill copies from.

```markdown
# <Project name>

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
`justfile` targets (`test`, `lint`, `dev`, `build`, `deploy`, `docs:generate`,
`docs:check`).

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

## The project CLAUDE.md template (canonical source)

Every scaffolded project also gets a `CLAUDE.md` explaining its structure and behavior — and, critically, the discipline for keeping the README current so it doesn't drift the way hand-maintained docs do. Stage 1 (#24) materializes this body under `templates/monorepo/CLAUDE.md` for scaffolding to consume via `${CLAUDE_PLUGIN_ROOT}`; until then, this is the source of truth.

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
2. Re-run `just docs:generate` (or the project's equivalent) so the root
   README reflects the change, and `just docs:check` before committing to
   catch drift.
3. Never hand-edit an aggregated section of the root README directly without
   also updating the fragment it came from — the next regeneration will
   silently overwrite a hand-edit that has no fragment behind it.
A stale README is treated as a bug: the `documentation` and `code-review`
skills flag it.
```

## "Ships its doc" is an acceptance bar

A template block, catalog component, or feature recipe is not done when its code works — it is done when its co-located doc fragment exists, is accurate, and is ready to aggregate. The `template-author` and `recipe-author` skills enforce this the same way they enforce the composition contract and the secure-by-default bar: an artifact without its doc fragment does not clear authoring. The `documentation` skill and `code-review` are the backstop for drift after the fact; the weekly freshness audit (Stage 12, #35) covers doc drift across the whole library.
