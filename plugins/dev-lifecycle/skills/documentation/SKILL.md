---
name: "documentation"
description: "Write and maintain technical documentation for a codebase — READMEs, API references, architecture decision records (ADRs), changelogs, contributing/onboarding guides, and inline docstrings/comments. Use this skill WHENEVER the work involves documenting code or a project: \"write a README\", \"document this API/endpoint/module\", \"add docstrings\", \"write an ADR\", \"update the changelog\", \"explain how to set this up\", or when a feature needs docs before it ships. It detects the project's existing documentation style and conforms. This is technical documentation — for resumes, proposals, or general prose, use the dedicated writing skills instead."
---

# Documentation

Write docs a real reader can act on, and that stay true to the code. The failure mode of documentation isn't being too sparse — it's being *wrong*: stale docs that describe code that no longer exists are worse than none. So the job is twofold: write the right doc for the reader, and keep it close enough to the code that it stays current.

Guiding idea: **document the *why*, not the *what*.** The code shows what it does; documentation captures intent, tradeoffs, constraints, and the reasoning behind a decision. A comment that restates the code is noise; one that explains why the obvious approach was rejected is gold.

## Core rules

- **Audience first.** Identify who reads this and what they need to do with it; write for that person's task, not a generic info dump.
- **Document the why.** Capture intent, tradeoffs, non-obvious constraints, rejected alternatives.
- **Keep docs current and close to code.** Put docs near the code and update them in the *same* change as the code they describe. A doc you won't keep updated shouldn't be written.
- **Right-size to the project.** A solo side project, a client deliverable, and an OSS library need very different amounts. Don't generate ceremonial docs nobody reads.
- **Show, don't just tell.** A concrete usage example or command beats paragraphs. Examples must actually work.
- **Detect and conform.** Match the project's existing doc style, structure, tone, and tooling.
- **Write like a human.** Clear, direct, specific; avoid filler and AI-sounding boilerplate. For heavier prose polish, the `humanizer` / `ruthless-edit` skills apply after.
- **Work context-efficiently.** Verify claims against the specific code, not the whole tree. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Workflow

### 1. Detect existing docs & the need
Read what's there (`README`, `docs/`, `CHANGELOG`, `CONTRIBUTING`, ADRs, docstring style) and match its conventions. Figure out which artifact the request needs and at what depth.

### 2. Identify the artifact
- **README / contributing / changelog / ADR** → `${CLAUDE_PLUGIN_ROOT}/references/docs/project-docs.md`.
- **API documentation / inline docstrings & comments** → `${CLAUDE_PLUGIN_ROOT}/references/docs/code-and-api-docs.md`.

### 3. Write it
Load the relevant reference. Lead with what the reader needs most; prefer working examples and real commands; be accurate over comprehensive — verify against the actual code. Produce real files in conventional locations (`README.md`, `CHANGELOG.md`, `docs/adr/NNNN-title.md`).

### 4. Hand off
Note what you documented and where, and flag anything you couldn't verify against the code. If it documents new code, remind that doc and code move together going forward.

## How this works with the other skills
- **planning / product-planning** decisions → **ADRs** (an epic's architecture decisions map onto an ADR). **backend** defines the API contract (FastAPI generates OpenAPI) → this writes the narrative API docs. **code-review** flags missing/stale docs → this addresses them.

## What this skill does NOT do
- Write comments/docs that merely restate the code. Produce docs it won't keep current. Over-document a small project. Invent behavior instead of describing what the code verifiably does. Replace the dedicated writing skills for non-technical prose.
