# pending-workflows/

Workflow files staged here are **proposed edits to `.github/workflows/`**
that a Claude session could not commit directly, because the GitHub App
this repo's automation runs under does not have the `workflows`
permission — any push that creates or modifies a file under
`.github/workflows/` is rejected. See
`plugins/dev-lifecycle/skills/scaffolding/SKILL.md`'s note on the same
constraint.

**A human must move/replace the target file by hand** (copy this file over
the top of the one in `.github/workflows/`, or `git mv`, then commit and
push — a human's own push isn't subject to the App's permission limit).

## `freshness-audit.yml` (Stage 12, issue #35)

Replaces `.github/workflows/freshness-audit.yml` in place — same filename,
so once placed it fully supersedes the current one.

### What changed
The current `.github/workflows/freshness-audit.yml` covers exactly one
thing: reference-library staleness, via a single `audit` job
(`contents: read` + `issues: write`) that opens a tracking issue. Its
prompt also says "Use the freshness-audit skill" — that skill does not
exist (`skills/freshness-audit` is absent from the plugin) — so the current
prompt is already partly broken.

This draft:
- **Keeps the `audit` job unchanged** — same permissions, same prompt,
  same tracking-issue behavior. Reference freshness is unaffected.
- **Adds a second job, `extended-audit`**, least-privilege split from the
  first: `contents: write` + `pull-requests: write` (the first job never
  gets write access; the second never gets `issues: write` since it doesn't
  need it). It runs a **self-contained prompt** — no reference to a
  nonexistent skill — covering four new dimensions:
  1. **Template version-drift / rebuild-verify** — each
     `templates/<layer>/<name>/README.md`'s `last-verified` +
     `versions-pinned-to` checked against `references/compatibility-matrix.md`
     and each dependency's current stable (grounded in official
     sources); flagged/touched blocks get materialized into a scratch
     monorepo and `just docs-check` / `just build` run against them.
  2. **Recipe version-drift** — each `references/recipes/*.md`'s
     `last-verified` and the component/matrix versions it wires, flagging
     superseded pins.
  3. **Compatibility-matrix drift** — every row in
     `references/compatibility-matrix.md` re-verified against upstream;
     flags a newer stable not adopted or a stale `last-verified` with an
     intervening release, while respecting the matrix's own documented,
     deliberate holds (pre-GA exclusions, `minimumReleaseAge` judgment
     calls) rather than flagging those as drift.
  4. **Doc drift** — deterministic half (`node scripts/docs-aggregate.mjs
     --check` against a materialized scratch project, catching
     README-vs-fragment drift with no LLM judgment involved) plus a
     Claude-driven comprehension half (fragment/README claims — env vars,
     ports, commands, routes — checked against the block's actual code).
- Both jobs keep the weekly `schedule` (Mondays 14:00 UTC) and
  `workflow_dispatch`, unchanged from today.
- `extended-audit` runs `python scripts/validate_plugin.py` and requires it
  to pass (0 errors) before opening anything — the validator remains the
  hard gate; this workflow does not bypass or duplicate it, it depends on
  it.
- Every proposed fix (a header, a pin bump, a regenerated matrix row) is
  marked `provenance: ... (pending review)` — audit PRs **propose**, they
  never self-promote to `provenance: manual`. A human merges the PR (or
  edits it first) the same way `coverage-audit.yml`'s PRs are merged today.
- `extended-audit` opens **at most one** PR per run
  (`freshness-audit/<YYYY-MM-DD>`, mirroring `coverage-audit.yml`'s
  `coverage-audit/<YYYY-MM-DD>` convention), and only if at least one of
  the four dimensions found something. No findings -> no branch, no PR —
  same "finish without changes" behavior `coverage-audit.yml` already uses
  for its own no-gaps case.

### Structure this reuses from `coverage-audit.yml`
The PR-opening job's shape (branch-per-run naming, `contents: write` +
`pull-requests: write`, the validator-then-PR sequencing, `cc @eblouin876`
in the PR body, self-contained prompt with no skill dependency, same
`anthropics/claude-code-action@v1` + `--model claude-sonnet-5` pin) is
lifted directly from `.github/workflows/coverage-audit.yml`, which is this
repo's existing template for a PR-opening scheduled audit.

## Acceptance criteria — how this design satisfies them

**Planted stale pin** (rolled-back `compatibility-matrix.md` row, or a
block README's `versions-pinned-to` line hand-set behind the matrix):
- Dimension 1 catches it on the template-block side (block pin vs. matrix
  vs. upstream current-stable); Dimension 3 catches it on the matrix side
  (matrix row vs. upstream current-stable) — whichever side was planted
  stale, the corresponding dimension's cross-check flags a version
  disagreement and the run opens a PR with the proposed bump marked
  `(pending review)`.
- Triggerable on demand via `workflow_dispatch` on the `extended-audit`
  job — no need to wait for the Monday cron; a human (or CI) can fire the
  workflow immediately after planting the drift and see the PR appear.

**Planted README/doc drift**:
- *Block code change without a fragment update* (e.g. a route or env var
  added to a block's app code but not reflected in its
  `docs/fragment.md` / README `exposes`): caught by Dimension 4's
  comprehension half — Claude compares the fragment/README's claims
  against the actual code and flags the mismatch.
- *Hand-edited aggregated region* (editing inside a
  `<!-- BEGIN block:<layer>/<name> --> ... <!-- END -->` region of a
  materialized project's root README directly, instead of through its
  fragment): caught by Dimension 4's deterministic half — regenerating a
  clean baseline with `just docs-generate` then running
  `node scripts/docs-aggregate.mjs --check` against the hand-edited README
  produces a non-zero exit with no LLM judgment needed, exactly matching
  what `docs-aggregate.mjs`'s own `--check` mode is built to do.

## Local proof (this session)

- `python3 scripts/validate_plugin.py` — ran clean (0 errors) with this
  file and `freshness-audit.yml` staged under `pending-workflows/`,
  confirming the validator's `.github/workflows/*.reusable.yml` and
  `plugins/dev-lifecycle/assets/workflows/*.yml` globs do not reach into
  `pending-workflows/`, so nothing here is held to the plugin's
  action-step or header-lint checks.
- `python3 -c "import yaml; yaml.safe_load(open('pending-workflows/freshness-audit.yml'))"`
  — parses clean.
- Deterministic doc-drift half, actually run in this sandbox: materialized
  a scratch monorepo (`/tmp/.../freshness-scratch/`) from
  `templates/monorepo/README.md.tmpl` (stripped to `README.md`) +
  `templates/monorepo/scripts/docs-aggregate.mjs` +
  `templates/packages/api-client/` (has a `docs/fragment.md`,
  `<!-- fragment: block:packages/api-client -->`). Sequence and results:
  1. `node scripts/docs-aggregate.mjs --check` against the untouched
     `.tmpl` skeleton (fragment not yet aggregated in) -> **exit 1**,
     correctly reporting drift (the sentinel-only baseline vs. the
     fragment's real content).
  2. `node scripts/docs-aggregate.mjs` (no `--check`) -> generated a clean
     baseline README with the `packages/api-client` fragment folded into
     its Setup/Maintenance marker regions.
  3. `node scripts/docs-aggregate.mjs --check` immediately after -> **exit
     0**, confirming the freshly generated README is recognized as
     up-to-date (no false positive).
  4. Hand-edited one line directly inside the
     `<!-- BEGIN block:packages/api-client --> ... <!-- END -->` Setup
     region (bypassing `docs/fragment.md` entirely, simulating the planted
     "hand-edited aggregated region" acceptance scenario) and re-ran
     `node scripts/docs-aggregate.mjs --check` -> **exit 1**, with the
     tool's own diff output pinpointing the exact injected line
     (`HAND-EDITED DRIFT: this line was typed directly into the aggregated
     README region, bypassing docs/fragment.md.`) as the first difference.
  This directly proves the acceptance criterion end-to-end: a hand-edited
  aggregated region is caught deterministically, non-zero exit, no LLM
  judgment involved — exactly what `extended-audit`'s Dimension 4
  deterministic half relies on.
