---
name: "recipe-author"
description: "Author a new feature recipe for this plugin's monorepo starter kit — what it wires across which blocks, its prerequisites, its wire-up steps, and its portable doc fragment, per the recipe template. Use this skill WHENEVER extending the starter kit's recipe catalog: \"add a feature recipe\", \"write a recipe for Stripe/S3/auth/...\", \"document how to wire up <feature> in the kit\". This is a META-skill invoked by build agents and humans EXTENDING the kit itself — not for wiring that feature into a specific app. For authoring the underlying template block a recipe composes, see template-author."
---

# Recipe author

A recipe is a portable how-to that composes already-authored template blocks and catalog components into one feature — Stripe checkout, S3 uploads, an auth provider — without inventing new infrastructure. This skill is the discipline for adding one: what it wires, what it needs already true, the concrete steps, and the doc fragment it contributes. It is invoked by build agents and humans extending the kit's recipe catalog, not by a build agent applying a recipe to a real project.

## Core rules

- **A recipe composes, it doesn't invent.** Every step references an existing block or catalog component by name; if the feature needs infrastructure that doesn't exist yet, author that block first (`template-author`), then the recipe.
- **Ground steps in current official docs.** Cite them in `sources` — a recipe that drifts from the vendor's actual current API is worse than no recipe.
- **Ships its doc, same as a block.** A recipe without its doc fragment does not clear authoring.
- **Subordinate to the project.** Note where a project's existing conventions would override a wire-up step; don't assume a clean slate.

## Workflow

### 1. Scope the recipe

Name it concretely (`stripe-checkout`, `cognito-auth`, `s3-uploads`) and identify which block(s)/stacks it `applies-to` (e.g. "fastapi only", "any frontend block"). Check the recipe catalog under `${CLAUDE_PLUGIN_ROOT}/references/recipes/` first — don't duplicate an existing recipe; extend it if the feature is a variant.

### 2. Author the recipe from the template

Copy the structure from `${CLAUDE_PLUGIN_ROOT}/references/recipes/_RECIPE-TEMPLATE.md` — the header (`recipe`, `applies-to`, `last-verified`, `provenance`, `sources`) and the body sections — into `${CLAUDE_PLUGIN_ROOT}/references/recipes/<name>.md`:

- **What this wires** — the concrete capability that exists once applied, and which blocks/components it touches.
- **Prerequisites** — which block(s) it `applies-to`, catalog components it depends on, required env vars/backing services, and the compatibility-matrix entries it's pinned to.
- **Wire-up steps** — an ordered, concrete list referencing components by name, not duplicating their content. Keep steps idiomatic for the pinned versions; flag anything version-sensitive inline.

### 3. Clear the bars this recipe touches

A recipe isn't itself a block, so it doesn't carry a full composition contract — but wherever it touches these surfaces, meet the same bars a block would, linked to the same canon:

- **Documented** — write the `## Doc fragment` section as a portable, ready-to-aggregate fragment (setup, any new env var and where to get it, maintenance), per `${CLAUDE_PLUGIN_ROOT}/references/authoring/documentation-standard.md`.
- **Version-pinned** — cite the governing entry in `${CLAUDE_PLUGIN_ROOT}/references/compatibility-matrix.md` for every version-sensitive step.
- **Secure-by-default** — wire-up steps default to the safe configuration (least-privilege keys, secrets never inlined, safe redirect/callback handling) per `${CLAUDE_PLUGIN_ROOT}/references/security/secure-baseline.md` — never leave the insecure option as the shown default.

### 4. Verify and hand off

Run `python scripts/validate_plugin.py`. Confirm every referenced block/component actually exists in the catalog under its cited name. Hand off by naming the recipe and what it now lets a scaffolded project do.

## What this skill does NOT do

- Apply a recipe to a real project — that's the relevant build skill, following the recipe once it exists.
- Author the template block a recipe wires into — that's `template-author`.
- Ship a recipe with an undocumented, unpinned, or insecure-by-default wire-up step.
