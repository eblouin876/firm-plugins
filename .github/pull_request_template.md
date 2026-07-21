<!--
PR template for the firm-plugins repo itself (the plugin/library, not a project
built with it). Keep it lean — fill what applies, delete what doesn't.
-->

## Summary
One or two sentences: what this PR adds/changes and why it belongs in the plugin.

## What changed / why
-

## Decision log
Judgment calls made while building this (naming, placement, anything a reviewer
should sanity-check rather than assume) — or "none" if there weren't any.

## Checklist
- [ ] `python scripts/validate_plugin.py` passes with 0 warnings (paste output below if any warnings were fixed)
- [ ] Every new/changed reference, template block, catalog component, or recipe has an updated `last-verified:` header
- [ ] Every new skill's frontmatter `name` matches its directory name
- [ ] A `release:major` / `release:minor` / `release:patch` label is set on this PR (see `release.yml`; default is patch if unset)
- [ ] Docs updated where relevant (root `README.md`, `docs/SETUP-AND-USAGE.md`, or an ADR for a significant decision)

## Validator output
```
<paste `python scripts/validate_plugin.py` output>
```

---
cc @eblouin876
