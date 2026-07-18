---
name: "coding-session"
description: "Run a whole piece of work end to end — from plan (or an existing epic/issue) through build, PR, review, and merge — by orchestrating the firm's lifecycle skills as subagents, with the human in the loop only at plan approval and merge. Use this skill WHENEVER the user wants to drive a feature or project from start to finish in one sitting rather than one step at a time: \"start a coding session\", \"let's build this end to end\", \"take this from plan to merge\", \"pick up this epic and build it\", \"run the whole pipeline on this\", \"work through this issue and keep going\". It is the conductor: it plans (or picks up scoped work), files/updates the GitHub issue structure and marks it in-progress, spawns a build subagent (frontend/backend/etc.) that opens a PR, spawns a review subagent that comments on the PR, loops build↔review to merge-ready, then notifies the user to merge and advances to the next scoped step until the work is complete. It never merges — the human merges — and it stops for approval before building."
---

# Coding session

A coding session is the conductor for a whole unit of work. The individual skills — `planning`, `frontend`/`backend`, `testing`, `code-review` — each do one job well; a coding session strings them together into the full **plan → issue → build → PR → review → merge → next step** loop and runs it, so you drive an epic or a feature from start to finish in one thread instead of hand-carrying each step.

It orchestrates by **spawning subagents**, one per stage of work, each briefed to invoke the right firm skill with a focused context. The conducting thread stays lean — it holds the plan, the issue numbers, and the loop state — while the heavy lifting (reading the codebase, writing code, reviewing a diff) happens in subagents whose context is thrown away when they finish. That's the token-efficiency doctrine at the session level: the orchestrator remembers *what* and *where*, the subagents do the *how* (`${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).

There are exactly **two human gates**: the user approves the plan before any code is written, and the user merges the PR. Everything between those gates runs autonomously. The session never merges — merge is the human's call (`${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`).

## Relationship to the headless Action pipeline

The firm has two ways to run the same loop, and this skill is one of them:

- **Headless Action pipeline** — `@claude` on a GitHub issue triggers the implement Action, which opens a PR; the review Action runs on the PR and routes `@claude`/`@owner` by outcome. It self-drives on GitHub with no thread attached. This is the fleet default for work kicked off from an issue.
- **Coding session (this skill)** — the loop is driven from an interactive thread using **local subagents**, so you watch it happen, keep a human in the loop at the two gates, and flow straight into the next scoped step when a PR merges. Use this when you're sitting down to build something and want to conduct it, not fire-and-forget.

They are compatible: a session files the same issue structure and opens the same kind of PR, so a piece of work can start in a session and be finished by the Action, or vice versa. Pick the session when a person is driving; pick the Action when the trigger is a GitHub event. Don't run both on the same issue at once — you'll get duplicate build agents racing on one branch.

## Core rules

- **Two gates, nothing more.** Stop for the user's approval before building (after the plan is filed) and stop for the user to merge (after review is clean). Do not invent extra check-ins; do not skip these two.
- **One scoped step at a time.** A session advances through scoped units — an epic's stages, or a single issue — building, reviewing, and merging **one** before starting the next. Never open parallel PRs for the same epic from one session; the loop is sequential so review and merge stay coherent.
- **Orchestrate, don't inline the work.** Spawn a subagent for each build and each review and let it invoke the firm skill. Don't write feature code or run the review yourself in the conducting thread — that bloats the orchestrator's context and defeats the point. The conductor reads the codebase only enough to write good subagent briefs.
- **The repo is the memory.** State lives in GitHub — the issue/epic, its `in-progress` label, the PR, the review comments — not in the thread. If the session is interrupted, another session (or the Action) can pick it up from the issue and PR alone.
- **Merge-ready is the ceiling, never merge.** The loop converges on `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`: behavior meets acceptance criteria, meaningful tests pass, CI green, security clean, review's blockers resolved. Then it **stops and notifies the user**. No agent self-merges.
- **Bound the loop, then escalate.** If build↔review can't reach merge-ready in a couple of rounds, or a finding needs a design decision, stop and bring it to the user with the diagnosis — don't thrash or force a risky change.
- **Route each subagent to the right model.** Reasoning-heavy stages (planning, plan-review, code-review) run on a stronger model; mechanical build/implementation runs on a cheaper one. Pass the model explicitly on every spawn (see "Model routing" below) — an unset model inherits the orchestrator's, which is the most expensive default and the main source of avoidable spend.

## Model routing

The session runs many subagents, and each is spawned with the `Agent` tool's `model` parameter. **Always set it** — leave it unset and the subagent inherits the orchestrator's model (Opus), which is the costliest option and the reason an un-routed session burns far more than it needs to. Route by what the stage actually demands:

| Subagent / stage | Model | Why |
| --- | --- | --- |
| **Orchestrator** (this conducting thread) | `opus` | Holds the plan, loop state, and gate decisions — reasoning-critical, and usually the session's own model already. |
| **Planner** (`planning` / `product-planning`, step 1) | `opus` | Investigation and design quality set the ceiling for everything downstream; cheap here is expensive later. |
| **Plan-review** (step 2) | `opus` | Judges whether a plan is actually buildable and what it glossed over — a judgment stage. |
| **Build / implementation** (`frontend`, `backend`, `testing`, `data`, `debugging`, `devops`, `infrastructure`; steps 4 and 6) | `sonnet` | Mechanical execution against a concrete plan — Sonnet builds to spec well and is where the bulk of tokens are spent, so this is the biggest saving. |
| **Code-review** (`code-review` pipeline mode; step 5) | `opus` | Correctness/security judgment — catching one real bug outweighs the token savings (`${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`). |

Rules of thumb:

- **Default reasoning/judgment stages to `opus`, execution stages to `sonnet`.** The split above is the default; follow it unless the user says otherwise.
- **The user can override per session.** If the user asks to run a stage cheaper (e.g. "review on Sonnet this time" for a low-risk change) or richer, honor it for that session — the defaults are a starting point, not a lock.
- **Match the model to the risk, not the file count.** A large but mechanical build is still `sonnet`; a small but subtle security-sensitive change may warrant keeping review (or even build) on `opus`. When a build step is unusually tricky, it's fine to raise that one spawn to `opus`.

## Workflow

### 1. Start the session — plan new, or pick up existing

Two entry points:

- **Plan new work.** The user is starting something fresh. Run the `planning` skill (or `product-planning` for a whole product) to investigate and draft the plan — spawn the planner on **`opus`** (see "Model routing"). Planning owns the investigate → draft → iterate loop; let it. Do **not** let planning file the issue and tag `@claude` yet — in a session, filing and the build trigger are the session's job (step 3), because the session drives the build with local subagents rather than the Action. Carry the approved plan into step 2.
- **Pick up an existing epic or issue.** The user points at an epic or issue already on GitHub. Read it (and its ADR/epic parent if any). If it's an **epic**, identify the next unstarted stage — the first `- [ ]` line / open sub-issue in roadmap order — and make *that stage* the scoped step for this pass; run `planning` on it if its issue is still a stub. If it's a **single issue** with an actionable plan already, use it as-is. Confirm with the user which scoped step you're picking up before proceeding.

Either way you arrive at **one scoped step** with a plan concrete enough to build from.

### 2. Verify the plan, then get approval (gate 1)

Before it becomes the build brief, the plan must be sound. Spin up a short **plan-review subagent** on **`opus`** (brief it with the plan + the relevant part of the codebase) to sanity-check it for completeness, feasibility, missing edge cases, and blast radius the plan glossed over — a cheap pass that catches "this plan can't actually be built as written" before a build agent discovers it the expensive way. Fold its findings back into the plan.

Then present the verified plan to the user and **iterate to explicit approval**. This is gate 1. Do not file anything or start a build until the user approves. If they request changes, revise and re-present.

### 3. Record the issue structure and mark it in-progress

On approval, file/update the work in GitHub in the right shape (this is `planning`'s step-5 behavior — reuse it, but the session performs it so it controls the trigger):

- **Single feature/fix** → one issue: title from the goal, body is the plan, step-by-step as a `- [ ]` task list. If it belongs to an epic, register it as a native **sub-issue** and add the `Epic: #<n>` marker + this issue's number on the epic's checklist line, so the epic reconciles on merge (see `planning`/`product-planning`).
- **Whole product / large effort** → epic + milestones + per-stage sub-issues (that's `product-planning`); then this session builds the stages one at a time.
- **Picking up an existing issue** → update it in place rather than filing a duplicate.

**Mark the active issue in-progress.** Apply an `in-progress` label to the scoped-step issue (create the label if the repo doesn't have one — a distinct color, description "actively being built in a coding session"). Label the epic in-progress too while a session is advancing it. Remove the label from the step issue when its PR merges (step 7); the closing issue is the completion signal, the label just says "a session has this right now" and prevents two drivers colliding.

Do **not** tag `@claude` on the issue — in a session the *session* drives the build via a local subagent (step 4), so tagging the Action too would start a second, racing build. (Tagging `@claude` is the handoff for the *headless* path, not this one.)

### 4. Build — spawn the build subagent

Pick the build skill from the nature of the scoped step, then spawn a subagent to do it — on **`sonnet`** by default (build is execution against a concrete plan; see "Model routing"), raising that one spawn to `opus` only when the step is unusually subtle or security-sensitive:

| Work is mostly… | Skill the subagent invokes |
| --- | --- |
| Client UI — components, pages, forms, styling | `frontend` |
| Server — endpoints, models, migrations, auth, jobs | `backend` |
| Both | brief the agent to use `frontend` **and** `backend`; if the step is large, prefer splitting it into a frontend sub-step and a backend sub-step and sequencing them |
| Tests are the deliverable | `testing` |
| Infra / CI / containers / deploy | `devops` (app pipeline) or `infrastructure` (hosting) |
| Data seeding or reporting | `data` |
| A diagnosed bug fix | `debugging` |

Brief the subagent with: the issue number and its plan/acceptance criteria, the specific skill to invoke, the target branch, and the bar — `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`. Instruct it to:

- Build to the plan on a feature branch, meeting **all** benchmarks — meaningful tests at the right levels, lint/type-check/tests green **locally**, security clean, docs moved with the code.
- **Open the PR itself** when green: `Closes #<issue>` in the body so the issue (and the epic box) reconciles on merge, a summary of what changed, and — per this repo's `CLAUDE.md` — a `cc @eblouin876` line so the owner is notified. (In other firm repos, follow that repo's PR conventions.)
- Report back the PR number/URL and anything it couldn't resolve.

Keep the conductor thread out of the file-by-file work — the subagent holds that context. When it returns, you hold just the PR number.

### 5. Review — spawn the review subagent

Spawn a second subagent to review the PR — on **`opus`** (correctness and security judgment; see "Model routing") — briefed to invoke the `code-review` skill in **pipeline mode** on that PR number. It reviews across all dimensions (correctness, conventions, DRY, security, performance), then posts its findings **as comments on the pull request** — per-finding comments with file:line, severity-ranked — and a single summary comment stating the verdict (merge-ready, or blockers/highs that must be fixed first). It stops at review; it does not merge and it does not push fixes itself in this mode.

Capture the verdict: **clean** (no blocker/high) or **changes needed** (with the specific findings).

### 6. Loop build ↔ review to merge-ready

- **Changes needed** → spawn a build subagent again (**`sonnet`**, same as step 4), briefed with the review's blocker/high findings (and the PR/issue context), to push fixes onto the **same PR branch**. Then spawn a review subagent again (**`opus`**) on the updated PR. Repeat.
- **Clean** → the PR meets the definition of done. Go to step 7.

Bound it: after ~2 rounds without convergence, or the moment a finding needs a human decision (a design trade-off, an ambiguous requirement, an architectural call), **stop and escalate to the user** with the specific blocker rather than looping again. A back-and-forth that isn't converging is a signal to pull the human in, not to spin.

### 7. Notify the user to merge (gate 2)

When review comes back clean, **notify the user in the thread**: the PR is merge-ready. Give the PR link, a one-line summary of what it does, confirmation that CI is green and review is clean, and — for an epic — which stage this is and what's left. Then **stop and wait**. This is gate 2; the session does not merge.

Once the user merges, the merged PR's `Closes #<issue>` closes the step issue, which (via the sub-issue link + `epic-checkoff`) ticks the epic's box. Remove the `in-progress` label from the merged step issue.

### 8. Advance to the next scoped step

- **Epic with stages remaining** → return to step 1's "pick up existing" path for the next `- [ ]` stage, and run the loop again (plan-verify → approval → issue → build → review → merge). Keep going until every stage is done.
- **Single issue, done** → the session is complete.

Announce each advance so the user always knows which step is active and how much remains.

### 9. Close out

When the epic/plan is fully merged: confirm the epic reads complete (all boxes ticked, all sub-issues closed), remove any lingering `in-progress` labels, and give the user a short wrap — what shipped, the merged PRs, and any follow-ups that surfaced but were left out of scope (file them as issues rather than dropping them).

## Subagent briefing notes

- **One skill focus per subagent.** A subagent is briefed to invoke a specific skill (or a build pair) with a specific issue/PR. Don't hand a subagent the whole session — hand it one stage of it. Its context dies when it returns; only what it reports (a PR number, a verdict, a blocker) survives into the conductor.
- **Set the model on every spawn.** Pass `model` on each `Agent` call per the "Model routing" table — `opus` for planner/plan-review/code-review, `sonnet` for build/implementation. An unset model silently inherits the orchestrator's (Opus); that inheritance is the single biggest source of avoidable session cost.
- **Pass pointers, not payloads.** Give the subagent the issue number and the branch and let it read what it needs from GitHub and the repo. Don't paste whole files into the brief — that's the orchestrator paying for the subagent's reading.
- **Isolate build agents that run concurrently only if they touch different trees.** In a normal session builds are sequential (one scoped step at a time), so isolation isn't needed. If you ever fan out, give each its own branch/worktree so they don't collide.
- **The review agent posts on the PR, not the issue** — follow-up work stays attached to the PR (matches `code-review`'s routing).

## What this skill does NOT do

- Merge, or advance past a merge-ready PR without the user merging. Ever.
- Skip either gate — build without plan approval, or continue to the next step before the current PR is merged.
- Tag `@claude` to trigger the headless Action while it's also driving the build locally (that races two build agents on one branch).
- Inline the build or the review into the conducting thread instead of spawning a subagent for each.
- Run several stages of one epic in parallel from a single session — the loop is one scoped step at a time.
- Open a duplicate issue when picking up existing work — update in place.
