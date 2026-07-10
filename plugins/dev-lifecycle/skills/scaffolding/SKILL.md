---
name: "scaffolding"
description: "Bootstrap a new or empty repository into the firm — project structure, tooling, a lean CLAUDE.md, and the full GitHub pipeline (the Claude Action, CI gates, branch protection) so the repo is ready to build through plan → PR → review → merge. Use this skill WHENEVER starting a greenfield project or standing up a repo you own: \"start a new project\", \"set up the repo\", \"scaffold this\", \"initialize the backend/frontend\", \"get this repo ready\", or as Stage 0 right after a product plan. This is for repositories you OWN and can commit to — for bringing in a repo you don't own without a footprint, use the onboarding skill instead. Backend defaults to Python, frontend to TypeScript, but it detects and conforms to any stack already present or intended."
---

# Scaffolding

Turn an empty (or barely-started) repository you own into a project that runs on the firm's pipeline. Scaffolding decides the structure, installs the tooling, writes the persistent project context, and wires the automation — so that from here on, work flows through the normal loop: a plan becomes a `@claude`-tagged issue, the build opens a PR, review takes it to merge-ready, CI gates it, and you merge.

The highest-leverage thing this skill produces is a lean `CLAUDE.md`: the one artifact that stops every later task from re-discovering the stack, so the whole pipeline stays cheap.

## Core rules

- **Owned repos only.** This skill commits infrastructure into the repo. If the repo isn't yours to commit to, stop and use the `onboarding` skill (guest mode), which sets everything up without a footprint.
- **Detect before you generate.** Even "greenfield" often has a partial setup. Read what exists first and conform; don't overwrite a convention that's already there.
- **Right-size, don't over-engineer.** Match the actual stack and scale. A solo/freelance app gets Docker + a PaaS target and simple CI — not Kubernetes, multi-env promotion, or ceremony it won't use. (See `${CLAUDE_PLUGIN_ROOT}/references/devops/deploy-operate.md`.)
- **Everything committed is deliberate.** The Action workflows, CI, branch protection, `.claude/settings.json`, and `CLAUDE.md` are the repo's contract with the pipeline. Never commit secrets.
- **Keep CLAUDE.md lean.** It's always in context — stable, high-value facts only (stack, versions, layout, commands, conventions), never a changelog or a tutorial. This is the token-efficiency payoff; see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.
- **Wire to the firm's gate.** The pipeline enforces `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`: CI green + a review, and **the human merges** — no self-merge.

## Workflow

### 1. Create or confirm the repo
Confirm this is (or will be) a repo you own — admin rights / able to install the GitHub App and commit workflows. If it's someone else's repo → hand to `onboarding`.
- **New app with no repo yet:** create it. `git init`, an initial commit, then `gh repo create <owner>/<name> --private --source=. --push` (or the API), and confirm the default branch. This is scaffolding's job — a brand-new app gets its repo here.
- **Repo already exists (empty or partial):** use it and conform to what's there.
This is the step that makes `product-planning` able to file its epic and milestones, so for a greenfield product, **scaffolding runs before the product plan is recorded**. If a `product-planning` epic already exists, this is Stage 0 of that roadmap — read the epic so the scaffold matches the planned architecture.

### 2. Determine the stack
Detect anything already present (manifests, lockfiles, framework config) and conform. For a true greenfield, apply the firm defaults unless the product plan says otherwise:
- **Backend:** Python — FastAPI + Pydantic v2 + async SQLAlchemy 2.0 + Postgres + Alembic (or Django where server-rendered + HTMX fits). See the backend references.
- **Frontend:** TypeScript — React (+ meta-framework by need) or server-rendered + HTMX. See the frontend references.
State the chosen stack and versions in a line before generating.

### 3. Lay down structure & tooling
- Project layout per the relevant build references (thin, conventional, mirrored front/back).
- Formatter/linter/type-checker config (Ruff + mypy/pyright for Python; ESLint/Biome + `tsc` for TS), a real `.gitignore` and `.dockerignore`, and an `.env.example` (never a real `.env`).
- A one-command local dev path (Docker Compose: app + Postgres) per `${CLAUDE_PLUGIN_ROOT}/references/devops/containers.md`.

### 4. Write the lean CLAUDE.md
Capture only what every future task needs: the stack and pinned versions, the project layout, the exact commands to run tests/lint/type-check/build/dev, and the load-bearing conventions. Point to the deeper docs rather than inlining them. Keep it short.

### 5. Wire the pipeline
- **Claude GitHub App + workflows:** an implement workflow (responds to `@claude` on issues/PRs) and a review workflow (PR-opened → the review agent). Install via `/install-github-app` or commit the workflow files.
- **CI gates:** lint → type-check → test → security scan, per `${CLAUDE_PLUGIN_ROOT}/references/devops/cicd.md`. A red gate blocks merge.
- **Branch protection:** require the CI checks and at least one review; disallow direct pushes to the default branch. Merge stays manual — yours.
- **Committed `.claude/settings.json`:** cost/efficiency env (`DISABLE_NON_ESSENTIAL_MODEL_CALLS`), sensible permissions (deny reads of `.env*`), and attribution per your preference for owned repos. This is what the cloud/Action agents inherit (they don't carry your user settings).

### 6. Hand off
Summarize what was scaffolded and how the repo now works: how to run it locally, what CI gates on, how a plan kicks off a build (`@claude`), and how a change reaches merge. If this is Stage 0 of a product roadmap, point to the next stage. The next move is a plan (`planning`), not code.

## What this skill does NOT do
- Scaffold a repo you don't own — that's `onboarding` (guest mode), which leaves no footprint.
- Over-engineer infrastructure beyond the project's real scale.
- Write feature code — that happens after a plan, via the build skills.
- Commit secrets, or bake them into images or settings.
