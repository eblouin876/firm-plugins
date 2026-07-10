---
name: "product-planning"
description: "Create the overarching plan for a whole product — the north star that keeps everything aligned — and break it into stages you build one at a time. Use this skill WHENEVER greenfielding a whole product or a major new system, or when the request is about the big picture rather than one feature: \"plan out the whole product\", \"what's the roadmap\", \"architect this from scratch\", \"break this into phases/milestones\", \"how should we stage this build\". It produces the product vision, the architecture and stack decisions, and a staged roadmap recorded as a GitHub epic + milestones + an ADR — then stops. It does NOT build anything or tag @claude; each stage is later planned and built through the normal planning → PR → review → merge loop. For scoping a single feature or fix, use the planning skill instead."
---

# Product planning

Chart the whole product once, so that everything built afterward stays aligned to it — then build stage by stage. This skill produces the *north star*: what the product is, the architecture and stack decisions that everything inherits, and the ordered roadmap of stages. It is design and decision-making only — no implementation code, and no `@claude` build trigger. You don't build a product all at once; you set up the stages and advance through them deliberately.

The plan lives as durable GitHub artifacts, not in chat — an epic issue, milestones, and an architecture ADR — so every later stage references a stable source of truth instead of re-deriving the product context. That's the "repo is the memory" principle at product scale (see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).

## Core rules

- **Plan the product, not the feature.** The output is vision + architecture + a staged roadmap, not a step-by-step build. Per-stage implementation detail is the `planning` skill's job, later.
- **Decisions here are load-bearing.** Stack, architecture, data model shape, auth approach, and cross-cutting conventions decided here constrain every stage. Record them so stages inherit them and don't re-litigate.
- **Stage for independent, shippable progress.** Order stages so each delivers something coherent and buildable on top of the last. A good Stage 1 is a thin end-to-end slice, not all of the backend.
- **Don't build, don't trigger.** No implementation code, no `@claude`. This skill sets up the roadmap and stops; you advance one stage at a time.
- **The roadmap is living.** As stages complete and you learn, revisit and adjust upcoming stages — it's a plan of record, not a contract in stone.

## Workflow

### 1. Frame the product
Establish what it is, who it's for, and what success looks like. If a `technical-proposal` exists (stack, why, cost), build on it rather than re-deciding. Pull out the constraints that shape architecture (scale, integrations, compliance, timeline).

### 2. Decide the architecture
Make the cross-cutting decisions every stage will inherit: the stack (defaulting to Python back / TypeScript front unless the proposal says otherwise — see the backend/frontend references), the high-level architecture, the core data model shape, auth, and the conventions the whole build follows. Note the key alternatives considered and why they were rejected — this is ADR material.

### 3. Build the staged roadmap
Break the product into an ordered set of stages. For each: what it delivers, why it comes in that order, its dependencies, and what "this stage is done" means (acceptance at the stage level, derived from `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`). Keep stages small enough to build and review as a unit.

### 4. Record it as durable artifacts
**A repo must exist first** — the epic, milestones, and ADR live in it. For a greenfield product with no repo yet, run `scaffolding` to create and initialize it (that's its job), then record the plan into it. Don't hand-wave this: no repo, nowhere to file the epic.
- **Epic / tracking issue** — the product plan: vision, architecture summary, and the roadmap as a checklist of stages (`- [ ]`), each linked to its milestone/sub-issue. This is the alignment anchor every stage references.
- **Milestones** — one per stage, so each stage's issues group under it.
- **Architecture ADR** — the decisions from step 2, via the `documentation` skill (its ADR format maps directly onto context / decision / consequences).
- Stub sub-issues per stage are fine as placeholders; they get fleshed out by `planning` when that stage begins.

Do **not** tag `@claude` — no stage is being built yet.

### 5. Hand off
Share the epic link and the roadmap at a glance. With the repo scaffolded and the plan filed, the next move is `planning` for Stage 1 — it reads this epic and the ADR, writes the stage's implementation plan, files it under the stage milestone, and tags `@claude`. Because every stage plan references the epic and ADR, alignment holds; `code-review` can check a stage against them.

So the full greenfield order is: `technical-proposal` (decide) → `scaffolding` (create & init the repo) → `product-planning` (file the epic/roadmap into it) → `planning` per stage.

## What this skill does NOT do
- Write implementation code, scaffolding, or configuration.
- Tag `@claude` or trigger any build — stages are advanced deliberately via `planning`.
- Produce per-stage step-by-step plans (that's `planning`, per stage).
- Re-decide settled architecture on every stage — the epic and ADR are the source of truth.
