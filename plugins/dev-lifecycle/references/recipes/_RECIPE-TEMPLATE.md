<!--
recipe: <name>                      # e.g. stripe-checkout, cognito-auth, s3-uploads
applies-to:                         # which stacks/blocks this recipe wires into
  - <block or stack>: <note, e.g. "fastapi only" or "any frontend block">
last-verified: <YYYY-MM-DD>         # date this recipe was last checked against the components/versions it wires
provenance: manual                  # manual | auto-generated (append "(pending review)" until reviewed)
sources:                            # official docs used to write or verify this recipe
  - https://...
-->

# <Recipe name>

One or two sentences on what feature this recipe delivers and why a project would reach for it. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Doc fragment

## What this wires
A short, concrete description of the feature this recipe assembles — which components/blocks it touches and what capability exists once it's applied. A recipe composes existing template blocks and catalog components; it does not invent new infrastructure.

## Prerequisites
What must already be true of the project before this recipe applies: which block(s) it `applies-to`, any component from the catalog it depends on, required env vars or backing services, and the compatibility-matrix entries it's pinned to.

## Wire-up steps
The concrete steps to apply the recipe, referencing components by name rather than duplicating their content:
1. <step, referencing the component/block it touches>
2. <step>
3. <step>

Keep steps idiomatic for the versions pinned in the compatibility matrix; note anything version-sensitive inline.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied — what a reader needs to know about this feature (setup, any new env var and where to get it, how it's maintained). See `${CLAUDE_PLUGIN_ROOT}/references/authoring/documentation-standard.md` for the doc-fragment model this feeds into.

```markdown
<!-- doc fragment template — replace with the recipe's actual contribution -->
### <Feature name>
- **Setup:** ...
- **Secrets:** <var> — obtained from ...
- **Maintenance:** ...
```

---
<!--
Authoring rules for a feature recipe:
- Ground every wire-up step in current official docs (cite in `sources`).
- Reference components/blocks by name; don't duplicate their content here.
- Ship the doc fragment — "ships its doc" is an acceptance bar the `recipe-author` skill enforces.
- Update `last-verified` whenever the recipe or the versions/components it wires change.
- This file (`_RECIPE-TEMPLATE.md`) is `_`-prefixed and skipped by header lint — it's the schema exemplar, not a real recipe. Real recipes use `recipes/<name>.md` without the underscore.
-->
