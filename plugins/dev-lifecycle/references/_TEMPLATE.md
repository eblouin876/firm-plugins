<!--
library: <name>                # e.g. react, sqlalchemy, material-ui
versions-covered: "<majors>"   # e.g. "18, 19" — what this doc's guidance is correct for
last-verified: <YYYY-MM-DD>    # date the guidance was last checked against current docs
provenance: manual             # manual | auto-generated (append "(pending review)" until reviewed)
sources:                       # official docs / release notes used to write or verify this
  - https://...
-->

# <Library> conventions

One or two sentences on what this reference covers and when a skill should load it. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- Version check (do this first)
- <the granular sections for this library>

## Version check (do this first)
The decisive version distinctions for this library, and how idiomatic code differs across them. State what changes between majors so code is written for the version actually installed. If unsure whether an API exists in the installed version, check the current official docs rather than recalling.

## <Sections>
Granular, current best-practice guidance. Concrete over abstract. Show the idiom; note the anti-pattern. Keep it to what changes how code is written — not a tutorial.

---
<!--
Authoring rules for this library reference:
- Ground every version-sensitive claim in current official docs (cite in `sources`).
- Keep it lean; this loads only when the library is detected in the project.
- Update `last-verified` and `versions-covered` whenever the doc is revised.
- The freshness audit reads the header above — keep it accurate.
-->
