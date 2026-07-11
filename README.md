# firm-plugins

A Claude Code plugin marketplace: the development firm's lifecycle skills and a self-extending, version-aware reference library. This repo is itself a project in the firm — changes go through the same plan → PR → review → merge → release pipeline as any other repo.

> Names (`firm-plugins`, `dev-lifecycle`) are placeholders — rename to taste before first publish.

## Install

```
/plugin marketplace add <owner>/firm-plugins
/plugin install dev-lifecycle@firm-plugins
```

Enable background auto-update in `/plugin` → Marketplaces, or refresh manually with `/plugin marketplace update`. (Auto-pull of git-sourced marketplaces can lag; a periodic manual update is the reliable fallback.)

## Layout

```
firm-plugins/
├── .claude-plugin/marketplace.json      # catalog (semver in metadata.version)
├── plugins/dev-lifecycle/
│   ├── .claude-plugin/plugin.json       # plugin manifest (semver)
│   ├── skills/<skill>/SKILL.md          # one folder per skill
│   ├── assets/workflows/                # canonical Action templates copied into each repo: implement + review (plugin + OAuth pre-wired) and epic-checkoff (ticks an epic's box on stage-issue close)
│   ├── assets/scripts/                  # operator one-shots — retrofit-epic.sh backfills a pre-existing epic so epic-checkoff works on it
│   ├── shared/                          # cross-skill references
│   │   ├── token-efficiency.md          # the efficiency doctrine every skill follows
│   │   └── definition-of-done.md        # the shared merge-ready bar
│   └── references/                      # the self-extending library, by domain
│       ├── frontend/  {react,typescript,tailwind,material-ui,htmx}.md
│       ├── backend/   {fastapi,sqlalchemy,postgres,pydantic,django}.md
│       ├── testing/ · devops/ · security/
│       └── _TEMPLATE.md                 # house format + metadata header
├── scripts/
│   └── validate_plugin.py               # structural validator (manifests + SKILL.md frontmatter)
└── .github/workflows/
    ├── validate.yml                     # runs the validator on every push/PR (merge gate)
    ├── release.yml                      # semver bump + tag on merged PR
    └── freshness-audit.yml              # weekly staleness check → tracking issue
```

Skills reference shared files and library references by plugin-root path, e.g. `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md` and `${CLAUDE_PLUGIN_ROOT}/references/frontend/react.md`. (Resolution is verified in the local plugin test; the fallback, if a path form doesn't resolve, is to copy the shared file into the skill's own folder.)

## Reference library conventions

References are **per-library**, not per-skill: one shared library the whole plugin loads from, so a doc is written once and every skill benefits. A build skill loads only the references for libraries actually detected in the project (progressive disclosure — see `shared/token-efficiency.md`).

Every reference carries a metadata header (see `references/_TEMPLATE.md`):

```
library · versions-covered · last-verified · provenance · sources
```

This header is load-bearing: it's what the freshness audit reads to decide staleness cheaply, and what distinguishes reviewed canon (`provenance: manual`) from machine-drafted docs (`provenance: auto-generated (pending review)`).

### Three ways a reference gets created or refreshed
1. **Onboarding (eager):** when a repo joins the firm, its significant direct dependencies are inventoried and any missing references are generated as a batch. Target frameworks/libraries with real idioms and version-sensitivity — not every transitive utility.
2. **Build-time (lazy):** if a build skill meets a library with no reference, it generates one for immediate use and opens a PR to add it here.
3. **Scheduled audit (freshness):** the weekly workflow flags references whose covered version or last-verified date has fallen behind; regeneration follows as a reviewed PR.

All three **ground generation in current official docs, never recall**, and all three land as **PRs you review and merge** — nothing enters canon silently.

## Releases (semver)

Version lives in `plugin.json` and `marketplace.json`. `release.yml` bumps it on a merged PR based on a label — `release:major` / `release:minor` / `release:patch` (default patch) — then tags. Users only receive updates when the version bumps, so an in-progress push never destabilizes a working session. Roll back by pointing the catalog entry at a prior tag/commit.

## Owned vs guest repos

- **Owned:** full in-repo pipeline — committed Action, branch protection, committed `.claude/settings.json` + `CLAUDE.md`. Set up by the `scaffolding` skill.
- **Guest (repos you don't own):** zero footprint. The skill library rides in via this user-installed plugin — nothing added to the repo. Project-local config goes in untracked files excluded via `.git/info/exclude`. Work runs under your own identity, so commits and PRs are yours; attribution is blanked (`{"attribution":{"commit":"","pr":""}}` in `~/.claude/settings.json`) and the `onboarding` skill scrubs any residual Claude attribution before push. Set up by the `onboarding` skill.

## Validation

`scripts/validate_plugin.py` checks the JSON manifests and the YAML frontmatter of every `SKILL.md` — the things Claude Code rejects on install. It runs in CI (`validate.yml`) on every push and PR, so a malformed skill can't be merged or shipped. Run it locally before pushing:

```bash
python scripts/validate_plugin.py
```

Make the `validate` job a **required status check** in branch protection so nothing merges without it. The workflow also runs the official `claude plugin validate` as a best-effort cross-check.
