# Setup & Usage — the development firm

How to stand up this plugin and run your projects through it: delegate work to agents, review and merge yourself, from any device, whether or not the road has good signal.

This is the operator's manual. The plugin's internal conventions are in the repo `README.md`; this doc is about *using* it.

---

## What you've got

A Claude Code plugin marketplace (`firm-plugins`) containing one plugin (`dev-lifecycle`) with:

- **18 skills** spanning the whole project lifecycle — `technical-proposal` → `product-planning` → `scaffolding` / `onboarding` → `planning` → `ui-exploration` / `design-system` → `backend` / `frontend` → `data` → `copywriting` → `testing` → `code-review` → `devops` / `infrastructure` → `dependency-maintenance` → `documentation` / `debugging`.
- A **self-extending reference library** of per-library, version-aware docs (React, TypeScript, MUI, Tailwind, HTMX, FastAPI, Pydantic, SQLAlchemy, Postgres, Django, plus testing/devops/security/docs/debugging).
- A **token-efficiency doctrine** every skill follows, and a shared **definition-of-done** that is the merge-ready bar.
- Two automations: **semver release** on merge, and a weekly **freshness audit** that flags stale references.

The spine is GitHub: issues are the task queue, PRs are work-in-review, CI is QA, **merge is yours**.

---

## One-time setup

### 1. Publish the marketplace
Push this repo to GitHub (private is fine):

```bash
cd firm-plugins
git init && git add . && git commit -m "firm plugin v0.1.0"
gh repo create <owner>/firm-plugins --private --source=. --push
```

### 2. Install the plugin
In Claude Code:

```
/plugin marketplace add <owner>/firm-plugins
/plugin install dev-lifecycle@firm-plugins
```

Turn on auto-update in `/plugin` → Marketplaces (or add `extraKnownMarketplaces` with `autoUpdate: true` to settings). Because the plugin is **user-scoped**, all 11 skills now follow you into *every* repo you open — including ones you don't own — with no per-repo install.

### 3. Your user settings (`~/.claude/settings.json`)
Applies everywhere you work, zero repo footprint:

```json
{
  "attribution": { "commit": "", "pr": "" },
  "env": { "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1" }
}
```

The blanked `attribution` is what keeps Claude out of commit/PR bylines on guest repos; `DISABLE_NON_ESSENTIAL_MODEL_CALLS` trims auxiliary model calls for cost.

### 4. Secrets for the automations
The firm authenticates with a Claude subscription token (OAuth), not an Anthropic API key.
- **Plugin repo:** add `CLAUDE_CODE_OAUTH_TOKEN` as a repo secret so the freshness audit can run. Install the Claude GitHub App on it if you want the plugin repo to dogfood the pipeline too.
- **Each owned project repo:** the `scaffolding`/`onboarding` skills set `CLAUDE_CODE_OAUTH_TOKEN` for you (`gh secret set`) when wiring the pipeline; you just install the Claude GitHub App once. No `ANTHROPIC_API_KEY` anywhere.

---

## Bringing a repo into the firm

### A repo you own → `scaffolding`
> "Scaffold this repo" / "set up a new project for X"

It detects (or defaults to Python back / TypeScript front), lays down structure and tooling, writes a **lean `CLAUDE.md`** (the thing that keeps every later task cheap), and wires the pipeline: the Claude Action (from the firm's workflow templates — plugin loaded and OAuth auth), CI gates, branch protection requiring CI + a review, and a committed `.claude/settings.json` the cloud/Action agents inherit.

### A repo you don't own → `onboarding` (guest mode)
> "Onboard this client repo without touching it"

Zero footprint: local config goes in untracked files excluded via `.git/info/exclude`, work is authored as you under your own `gh` auth, commits/PRs carry no Claude attribution (blanked + scrubbed before push), branches are neutrally named, and there's no in-repo Action. You drive the builds yourself; the repo owner sees only your work, as you.

---

## Daily workflow

### A whole new product (greenfield)
1. **`technical-proposal`** — "What should we build this with, and what will it take?" Recommends the stack + architecture, justifies it, and gives an honest cost/timeline. The build/no-build decision.
2. **`scaffolding`** — creates and initializes the repo (`gh repo create`, structure, tooling, lean `CLAUDE.md`, pipeline wiring). This is what gives `product-planning` a place to file its epic.
3. **`product-planning`** — "Plan out the whole product." Produces the north star: vision, architecture/stack decisions, and a **staged roadmap** as a GitHub **epic + milestones + an ADR** in the repo. It stops there — no build.
4. **Per stage**, repeat: **`planning`** reads the epic + the stage stub, you go back and forth until you approve, then it files the stage issue under its milestone and tags **`@claude`**. The build agent implements and opens a PR → the **review agent** takes it to merge-ready → **CI** runs → **you merge** → **`devops`** deploys (Goatenheim beta, or your chosen target) → next stage.

Because every stage plan references the epic and ADR, the whole product stays aligned to the north star.

### A feature or fix on an existing repo
1. **`planning`** — talk it through; on your approval it files the issue and tags `@claude` (owned repos) or hands it to you to run (guest repos).
2. Build agent → PR → review agent → CI → **you merge**.

### The one rule that never changes
Agents plan, build, review, and get to green — **you approve the plan and you merge.** No agent ever merges.

### From any device / bad signal
Once a task is dispatched, it runs server-side (a cloud sandbox or the GitHub Action) — independent of your connection. Kick it off, close the laptop, lose Starlink; it keeps going. Check status, review the diff, and merge from the Claude mobile app's remote-control panel or GitHub mobile. Heavier or private work can run on **Goatenheim** over Tailscale and be reviewed the same way.

---

## The reference library

References are **per-library and version-aware**, loaded only when that library is detected — so a task pulls in exactly the docs it needs and nothing more.

**Three ways the library grows/stays fresh** (all land as PRs to the plugin repo that *you* review and merge — nothing enters canon silently, and everything is grounded in current official docs, never recall):
- **Onboarding** inventories a repo's significant dependencies and generates any missing references in a batch.
- **Build-time** fills a gap on the spot if a skill meets a library with no reference.
- **The weekly freshness audit** compares each reference's `versions-covered` / `last-verified` header against the library's current release and flags stale ones in a tracking issue.

---

## Maintaining the plugin

The plugin is itself a project in the firm — improve it through the same loop:
1. A change (new skill, edited reference, freshness fix) comes in as a **PR** to `firm-plugins`.
2. CI validates; **you review and merge**.
3. On merge, `release.yml` bumps the **semver** version (label the PR `release:major|minor|patch`, default patch) and tags it.
4. Your installs pick it up on auto-update, or run `/plugin marketplace update`.

Roll back by pointing the catalog at a prior tag.

---

## Which skill for what

| I want to… | Skill |
|---|---|
| Decide whether/what/what-it-costs to build | `technical-proposal` |
| Plan a whole product and its stages | `product-planning` |
| Plan one feature/fix and kick off the build | `planning` |
| Start a new repo I own | `scaffolding` |
| Work a repo I don't own, invisibly | `onboarding` |
| Build server-side code | `backend` |
| Build UI | `frontend` |
| Explore new UI and turn it into a spec | `ui-exploration` |
| Define/enforce design tokens | `design-system` |
| Write product/UI copy | `copywriting` |
| Write/deepen tests | `testing` |
| Review a diff or run the PR review agent | `code-review` |
| Containerize, wire CI, deploy (incl. Goatenheim) | `devops` |
| Provision & maintain hosts/infra (AWS, home, Tailscale) | `infrastructure` |
| Keep dependencies current / patch a CVE | `dependency-maintenance` |
| Seed data & build reports | `data` |
| Write docs / ADRs / API reference | `documentation` |
| Root-cause a failure | `debugging` |

---

## What's not done yet

- **Testing pass:** each skill should get the skill-creator trigger-eval in Claude Code before you rely on it heavily, and the `${CLAUDE_PLUGIN_ROOT}/shared/...` reference paths should be confirmed to resolve once the plugin is installed (fallback: copy shared files into each skill's folder).
- The `release.yml` semver logic and `freshness-audit.yml` prompt are solid v1s to refine in practice.
