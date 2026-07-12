---
name: "dependency-maintenance"
description: "Keep a project's dependencies current and secure — audit for outdated and vulnerable packages, plan and apply upgrades safely, and remediate CVEs. Use this skill WHENEVER the work is about the dependency graph rather than features: \"update our dependencies\", \"are we vulnerable to X\", \"bump this to the latest\", \"there's a CVE in Y\", \"why is npm/pip audit complaining\", \"upgrade to React/Django N\", or on a periodic maintenance sweep. It grounds fixed versions and severities in current advisories, upgrades incrementally so breakage is bisectable, and ships every change through the normal pipeline. This is the project-dependency counterpart to the plugin's own freshness audit."
---

# Dependency maintenance

Keep the software supply chain current and safe. This is the code-side complement to `infrastructure` (host maintenance) and to the plugin's freshness audit (which keeps *our references* current — this keeps a *project's dependencies* current). In a full-project `security-audit`, this dependency sweep is one surface of many — that skill maps the whole attack surface; this one remediates the dependency slice. The two failure modes it prevents: falling so far behind that upgrades become dangerous, and sitting on a known vulnerability.

## Core rules

- **Detect the ecosystem and its tools.** Read the manifest/lockfile; use the native audit (`pip-audit`, `npm audit`) and any configured automation (Dependabot/Renovate). Conform to what's there.
- **Upgrade safely and incrementally.** Understand semver risk: patches/minors are usually safe; **a major is its own PR** with changelog/migration review. One logical upgrade per PR so a regression is bisectable. Lean on the test suite and CI gates to catch breakage.
- **Security first, scaled to risk.** Prioritize known-exploited and high-severity CVEs. Assess **reachability honestly** — is the vulnerable code path actually used? — then patch to the fixed version. Don't let a scary-sounding advisory in an unreachable dep jump the queue over a reachable one.
- **Ground in current advisories.** Fixed versions and severities come from official sources (GitHub Advisory Database, NVD, the ecosystem's own notes) — **not recall**. Advisories and patched versions change; check them.
- **Don't upgrade for its own sake.** Currency and security are the goals, not chasing latest. Weigh churn against benefit; pin deliberately where stability matters.
- **Everything through the pipeline.** Upgrades are PRs that pass the gates and get reviewed and merged like any change.

## Workflow

### 1. Audit
Run the ecosystem's audit and list what's **outdated** and what's **vulnerable**, with the fixed version for each. Distinguish **direct vs transitive** dependencies (a transitive fix may need a direct bump or an override). The CI security gate already scans this (`${CLAUDE_PLUGIN_ROOT}/references/devops/cicd.md`, OWASP A03 in `${CLAUDE_PLUGIN_ROOT}/references/security/owasp.md`).

### 2. Triage & prioritize
Security fixes first, ordered by severity **and reachability**; then meaningful currency upgrades; defer low-value churn. Mark each as safe (patch/minor) or breaking (major).

### 3. Plan the path
Batch patches/minors that are low-risk. Give **each major its own PR**, having read its changelog/migration guide. For a CVE, identify the fixed version and the **minimal** change to reach it (a targeted bump beats a sweeping upgrade under time pressure).

### 4. Apply & verify
Upgrade, then run tests + type-check + build. For a major, follow the migration guide and fix fallout via the `frontend`/`backend` skills. Confirm the vulnerable path is actually gone, not just the version number changed.

### 5. Ship
PR → review → CI green → merge, per `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`. For an urgent CVE, expedite the review but **don't skip the gates** — a rushed broken fix is its own incident.

### 6. Hand off
What was upgraded/patched, what a major changed (and any follow-up), and anything deferred with the reason.

## What this skill does NOT do
- Upgrade blindly or for its own sake — churn without benefit.
- Bundle a major bump with unrelated upgrades (unbisectable).
- Skip tests or gates on an "urgent" fix.
- Rely on recall for fixed versions or severities — verify against current advisories.
