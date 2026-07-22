---
name: "security-audit"
description: "Run a thorough, whole-project security audit — fingerprint the application type, map every applicable attack surface, credit what's already mitigated with evidence, identify open vulnerabilities, deliver an inline audit report, and (after one confirmation) file each finding as a scoped, pipeline-ready GitHub issue. Use this skill WHENEVER the user asks for a security assessment of a project as a whole: \"security audit\", \"how secure is this app\", \"find vulnerabilities\", \"map the attack surface\", \"pentest prep\", \"is this safe to launch\", \"harden this app\". This is the whole-codebase, point-in-time audit — distinct from code-review (which checks one diff's security as it ships) and dependency-maintenance (which remediates the dependency graph; this audit covers it as one surface). Strictly read-only: it never fixes code and never runs exploits — remediation flows through the filed issues into the normal plan → PR → review pipeline."
---

# Security audit

A point-in-time, evidence-based security assessment of the whole project. `code-review` guards each diff as it ships; this skill audits the accumulated whole — what the application exposes, what is already defended (credited, with evidence), and what is open (rated, reported, and filed as buildable issues). The deliverables are an inline audit report and, after the user confirms, one scoped issue per finding so remediation runs through the normal plan → PR → review → merge pipeline.

## Core rules

- **Read-only, always.** Never modify code or config, never run exploits, credential attacks, or anything that mutates state or probes a live system. Only non-mutating commands: audits, greps, config reads. This makes the audit safe on any repo, including guest repos (`onboarding`).
- **Evidence or it didn't happen.** Every claim — handled *or* finding — cites `file:line` (or the config/CI path). Judge reachability honestly, per `${CLAUDE_PLUGIN_ROOT}/references/security/owasp.md`. No speculative findings padded for volume; no soft-pedaling a real hole to be agreeable.
- **Credit what's handled.** Half the audit's value is telling the user what they *don't* need to worry about. "Handled" is held to the evidence standard in `${CLAUDE_PLUGIN_ROOT}/references/security/attack-surfaces.md` — the control located and confirmed wired in, not presumed from the framework.
- **Scale to the application type.** Fingerprint first, then assess only the surfaces that apply. A CLI tool doesn't get audited for CSRF; a library doesn't get audited for session handling.
- **No silent gaps.** If a scanner isn't installed, a surface couldn't be assessed, or git history wasn't scanned, the report says so explicitly. A security report that hides its own blind spots is worse than none.
- **Report first, one confirmation, then issues.** The user sees the full findings inline before anything is written to the repo. Never file issues before that confirmation.
- **Public-repo disclosure guard.** Check repository visibility before filing. On a public repo, a detailed vulnerability issue is public disclosure — warn the user and offer redacted issues (title + severity + pointer, exploit detail stays in the inline report) before filing anything.
- **Token-efficient breadth.** Whole-project scope does not mean whole-tree reads: enumerate surfaces from structure, route tables, and config, then read the specific spans that decide handled vs open. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Severity scale

🔴 **Critical** — exploitable now with serious impact (auth bypass, injection, exposed secrets, cross-tenant access). 🟠 **High** — real vulnerability, harder to reach or lower blast radius. 🟡 **Medium** — weakens posture or a missing defense-in-depth layer. ⚪ **Low** — hardening opportunity. ✅ **Handled** — control present and verified. Rate by impact × exploitability, not by how alarming the category sounds.

## Workflow

### 1. Fingerprint the application
Establish what kind of thing is being audited: application type(s) — web frontend, HTTP API/backend, background workers, CLI, library/package, infra/IaC/CI-CD; most projects are several at once — plus stack and versions (from manifests), entry points, trust boundaries, data sensitivity (PII? payments? credentials?), and deployment context (internet-facing? multi-tenant?). State which sections of `${CLAUDE_PLUGIN_ROOT}/references/security/attack-surfaces.md` apply. This fingerprint scopes everything that follows.

### 2. Enumerate the attack surfaces
Instantiate the applicable taxonomy sections against *this* project: the actual routes, input channels, upload paths, webhooks, jobs, workflows — located by search, not by reading the tree. The enumeration doubles as the report's attack-surface map and the audit's checklist.

### 3. Assess each surface
For each enumerated surface, read the deciding spans and classify: ✅ Handled (evidence cited), 🔴/🟠/🟡/⚪ finding (impact, evidence, remediation sketch), or N/A (one line why). Use `${CLAUDE_PLUGIN_ROOT}/references/security/owasp.md` as the per-surface vulnerability checklist. Also assess each surface against `${CLAUDE_PLUGIN_ROOT}/references/security/secure-baseline.md`, crediting what it satisfies and faulting what it violates alongside the OWASP-based findings.

### 4. Run mechanical scans (read-only)
- **Dependencies:** the ecosystem's native audit (`pip-audit`, `npm audit`), per `dependency-maintenance` conventions — results fold in as the supply-chain surface.
- **Secrets:** pattern scan of the tree and git history (`gitleaks` if available; targeted grep for key/token/password patterns otherwise).
- **Config:** debug flags, exposed docs/admin endpoints, CORS, security headers, Dockerfile/CI hygiene — checked against `${CLAUDE_PLUGIN_ROOT}/references/security/secure-baseline.md`'s CI-scanning, security-headers, and CORS-lockdown sections, not just general judgment.

Record every scan that was skipped and why — these go in the report's scope section.

### 5. Deliver the inline audit report
Present in the conversation, in this shape:
1. **Executive summary** — overall posture in 3–5 sentences, finding counts by severity.
2. **App profile & scope** — the fingerprint, what was assessed, and *what was skipped*.
3. **Attack-surface map** — the enumeration from step 2.
4. **What's handled** — credited controls with evidence.
5. **Findings** — severity order; each with impact, evidence (`file:line`), and a remediation sketch.
6. **Remediation roadmap** — findings ordered by risk and by dependency between fixes (fix the auth bypass before rate-limiting it).

### 6. Confirm, then file the issues
After the user confirms (and the visibility check from Core rules passes):
- An umbrella issue **"Security audit YYYY-MM-DD"** — posture summary and a severity-ordered task list (`- [ ]`) of the findings, labeled `security`.
- **One issue per 🔴/🟠 finding; related 🟡/⚪ findings grouped by theme** to avoid issue spam. Each in the `planning` skill's issue format (goal / context / steps / acceptance criteria) so it is directly buildable, labeled `security` plus severity, registered as a native sub-issue of the umbrella, with its number on the umbrella's checklist line so the epic reconciles when it closes.
- **Do not tag `@claude` on any of them.** An audit can produce a dozen issues; auto-triggering that many builds is chaos. The user picks which to kick off — or asks to tag the criticals, one at a time.

### 7. Hand off
The report stands delivered; share the umbrella and finding-issue links, the single highest-priority next step, and confirm nothing in the repo was modified.

## What this skill does NOT do

- Modify code or config, or apply any fix — remediation goes through the filed issues into the pipeline.
- Run exploits, brute force, denial-of-service, or anything against live systems — static and config analysis with read-only scans only.
- File issues before the user has seen the report and confirmed — or file detailed vulnerabilities on a public repo without an explicit go-ahead.
- Tag `@claude` on finding issues — the user controls build kickoff.
- Replace the `code-review` security gate (per-diff, every PR) or `dependency-maintenance` (the remediation lane for dependency CVEs).
- Manufacture findings to look thorough, hide its own blind spots, or bury a real hole.
