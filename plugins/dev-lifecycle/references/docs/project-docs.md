<!--
library: documentation
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Project & process docs (README, contributing, changelog, ADRs)

Guidance for the docs that orient people to a project and record its decisions. Read after deciding which artifact you're writing. The project's existing conventions override anything here.

## Contents
- README
- Contributing / onboarding
- Changelog
- Architecture Decision Records (ADRs)

## README
The front door. A reader should learn what the project is and get it running fast. Lead with the essentials; push depth down or into `docs/`.

Typical structure (include what's relevant, drop what isn't — right-size to the project):
- **One-line description** of what it is and who it's for, up top.
- **Quick start** — the shortest path to running it: prerequisites, install, run. Exact, copy-pasteable commands. For a containerized app, the `docker compose up` path. Verify the steps actually work.
- **Usage** — the common things a user/developer does, with concrete examples.
- **Configuration** — required env vars (point to `.env.example`), not secrets themselves.
- **Project layout** — a short orientation to the main directories, if non-obvious.
- **Development** — how to run tests, linting, and the app locally (or link to CONTRIBUTING).
- **Deployment** — how it ships, or a link to that doc.
- **License / links** as appropriate.

Keep it scannable: headings, short paragraphs, fenced code blocks. The README is read more than any other doc — every claim in it should be true *today*.

## Contributing / onboarding
For projects others (or future-you) will work on:
- How to set up a dev environment from a clean machine — prerequisites, install, run, seed data.
- How to run tests, linters, type-checks, and the pre-PR checklist (mirror what the CI gate enforces, so locals match CI).
- Branching/commit/PR conventions the project uses.
- Where to ask questions / how decisions are made.
Keep it to what someone actually needs to be productive; link rather than duplicate the README.

## Changelog
Follow **Keep a Changelog** conventions with **Semantic Versioning** unless the project does otherwise:
- Reverse-chronological; newest at top. An `## [Unreleased]` section accrues changes between releases.
- Group entries under **Added / Changed / Deprecated / Removed / Fixed / Security**.
- Write entries for **humans**, describing the impact of a change — not raw commit messages or PR titles.
- On release, rename `[Unreleased]` to the version with a date and start a fresh `[Unreleased]`.
- SemVer: MAJOR for breaking changes, MINOR for backward-compatible features, PATCH for fixes. Call out breaking changes prominently.

## Architecture Decision Records (ADRs)
A short doc capturing one significant technical decision and *why*, so future readers don't have to reverse-engineer the reasoning or relitigate it.

- Store as numbered files: `docs/adr/0001-short-title.md`, incrementing.
- ADRs are **immutable once accepted** — don't rewrite history. If a decision changes, write a new ADR that supersedes the old one and mark the old one superseded.
- A lightweight, widely-used structure:
  - **Title & number**
  - **Status** — proposed / accepted / superseded (by which ADR)
  - **Context** — the forces and constraints that made a decision necessary
  - **Decision** — what was chosen, stated plainly
  - **Consequences** — the resulting tradeoffs, both the good and the costs you're accepting
- Keep it to a page. The value is the rationale and the rejected alternatives, not length.
- A plan from the planning skill often contains exactly this material — its proposed approach, alternatives considered, and risks map cleanly onto Context / Decision / Consequences.
