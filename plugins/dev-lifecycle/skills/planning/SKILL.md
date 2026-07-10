---
name: "planning"
description: "Produce a clear, actionable implementation plan before any code is written, then — once the user approves it — file it as a GitHub issue and hand it to the build pipeline. Use this skill WHENEVER the user asks to plan, scope, design, or \"figure out how to approach\" anything — a new project, a feature, a refactor, a performance push, a bug fix, or a technical investigation. Trigger it even when the user doesn't say the word \"plan\" but is clearly asking how something should be built or fixed (e.g. \"how would we add X\", \"what's the best way to tackle Y\", \"I need to fix this bug\"). Planning is investigation and design only — it never writes or runs implementation code. It gathers context efficiently, proposes an approach, iterates with the user to approval, then records the approved plan as a GitHub issue and tags @claude to start the build."
---

# Planning

A plan is a thinking artifact, not a coding session. Understand the problem, learn what already exists, lay out a concrete path forward — then stop, get the user's approval, and only then file it and kick off the build. No implementation code is written here; none of it would be run or reviewed at this stage, so writing it now just burns context and pre-commits to decisions the plan hasn't justified.

Planning is the entry point to the pipeline: the approved plan becomes a GitHub issue, and tagging @claude on that issue starts the build agent (the frontend/backend skills) that opens the PR. So the plan is also the build agent's brief — it must be clear enough to implement from.

## Core rules

- **Investigate, don't implement.** Read and search the codebase as needed. Do not write feature code, scaffolding, or migrations. Tiny illustrative snippets (a few lines showing an interface shape or a data model) are fine when they make the plan clearer; full implementations are not.
- **Work context-efficiently.** Context is the budget. Locate with search before reading; read the specific spans that change the plan, not whole files or directories; state reasonable inferences as assumptions rather than verifying everything. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.
- **Stop for approval.** Present the plan and iterate on feedback. Do NOT file the issue or tag @claude until the user explicitly approves. The plan is the deliverable; the user's approval is the trigger.
- **Detailed but concise.** Every section earns its place. A senior engineer — or the build agent — should be able to read the plan and start building. Cut throat-clearing, restating the obvious, and filler.

## Workflow

### 1. Classify the request

Identify which kind of plan this is, because it changes what context matters and how the plan is shaped:

- **Greenfield project** — nothing exists yet. Focus on architecture, stack choices, and the initial build order. There's no codebase to read.
- **New feature / push** — adding to an existing codebase. The bulk of the work is understanding what's already there and where the new work plugs in.
- **Bug fix** — something is broken. The plan centers on root-cause investigation, not just the surface symptom.
- **Refactor / migration** — changing structure without (ideally) changing behavior. Emphasis on blast radius, sequencing, and how to keep things working throughout.

If the request is ambiguous about scope, ask one focused clarifying question before investigating — but only if the ambiguity would meaningfully change the plan. Otherwise proceed and note the assumption.

### 2. Gather context (skip for greenfield with no codebase)

Understand the problem and the current state of the relevant code well enough to propose a sound approach — and no more. Efficiency matters most here (see `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).

- Locate the relevant area with search before reading — directory structure, file/function names, grep for symbols. Then read only the specific code the change touches or depends on, not whole files or trees.
- Trace the relevant data flow: where the data comes from, what transforms it, where it ends up.
- Note existing patterns and conventions (how similar features are built, naming, error handling, test style) so the plan fits the codebase rather than fighting it.
- For bug fixes, find the actual mechanism, not just the symptom. Form a root-cause hypothesis and identify the evidence for it.
- Stop gathering once each plan section can be written with justified confidence. If a detail can't be resolved cheaply, surface it as an open question rather than spelunking.

### 3. Write the plan

Compose the plan using the structure below. Adapt section depth to the size of the work — a one-line bug fix doesn't need the heft of a new service. Omit a section only if it genuinely has nothing to say.

```
## Goal
One or two sentences: what we're building/fixing and why it matters.

## Current state & context
What already exists that's relevant. For brownfield: the specific files,
functions, models, and patterns involved, with paths. For bug fixes: the
root cause and the evidence for it. For greenfield: the chosen stack and
high-level architecture, with brief rationale.

## Proposed approach
The strategy at a conceptual level before the step list — the key design
decisions and why. Call out alternatives considered and why they were
rejected, when the choice isn't obvious.

## Step-by-step breakdown
An ordered list of concrete, reviewable steps. Each step names what
changes (which files/modules/endpoints), and is small enough to verify on
its own. Note dependencies between steps and anything parallelizable. This
is the heart of the plan and the build agent's checklist.

## Risks & open questions
Things that could go wrong, decisions that need the user's input, unknowns
that couldn't be resolved cheaply, and anything that would change the plan
if the answer were different.

## Acceptance criteria
How we'll know it's done and correct. Derive these from the shared
merge-ready bar in ${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md — observable behavior,
the edge cases to cover, and what testing the implementation should
include. These become the build agent's target and the testing skill's
checklist.
```

### 4. Review with the user and get approval (the gate)

Present the plan in the conversation. Discuss, adjust, and iterate on the user's feedback until they **explicitly approve**. This is the back-and-forth, and it may take several rounds. Do not file anything or trigger the build during this step. If the user requests changes, revise and re-present. Only explicit approval moves to step 5.

### 5. Record the approved plan and kick off the build

On approval, and only then:

- **File a GitHub issue.** Title from the goal; body is the plan; render the step-by-step breakdown as a markdown task list (`- [ ]`) so progress can be checked off. Prefer `gh issue create`; fall back to the GitHub API. For a large effort, a tracking issue with linked sub-issues is fine, but a single well-structured issue is the default.
- **Tag @claude to start the build.** Trigger the build agent by mentioning @claude on the issue (e.g. a comment: "@claude implement this plan"), so the Claude GitHub Action picks it up, implements against the plan, and opens a PR.
- **If the Action isn't installed on the repo,** file the issue but note @claude won't respond until the repo is scaffolded into the pipeline (see the `scaffolding` skill).
- **If GitHub isn't available** (no `github.com` remote, or the CLI/API can't create issues), present the plan inline, say plainly it couldn't be filed, and note the build wasn't auto-triggered. Never silently drop the plan.

Filing the issue and tagging @claude is recording and delegating, not implementing — this does not violate "investigate, don't implement." Planning still writes no code; the build agent does.

### 6. Hand off

Share the issue link and a one-line summary, and note that @claude has been tagged and the build is running in the pipeline (a PR will follow). The next checkpoint is the user's: reviewing the PR the pipeline produces.

## What this skill does NOT do

- Write production code, scaffolding, config, or migrations.
- Run code, tests, or commands that mutate state — beyond creating the issue once the user has approved.
- File the issue or trigger the build before the user approves the plan.
- Read whole files or directories when a targeted search and a specific span would do.
- Pad the plan with generic best-practice boilerplate not specific to this work.
