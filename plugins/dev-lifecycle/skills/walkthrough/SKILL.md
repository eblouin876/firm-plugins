---
name: "walkthrough"
description: "Explain a file, a section/subsystem of a repo, or a pull request in depth — what the code does, WHY it was built that way (decisions, tradeoffs, constraints), and what future considerations matter — as inline, human-readable markdown with links to the relevant docs and code. Use this skill WHENEVER the user wants to understand code rather than change or judge it: \"walk me through this file\", \"explain this PR / what changed and why\", \"how does this subsystem work\", \"why was this built this way\", \"help me get my head around this module\", \"onboard me to this part of the codebase\". It is read-only and outputs inline — it writes no files and posts no comments. This is comprehension: for issue-finding use code-review, and for writing durable docs (README/ADR/docstrings) use documentation."
---

# Walkthrough

Explain a piece of code so someone can *hold it in their head* — not just what it does, but why it's shaped this way and what to watch out for next. The output is a guided tour that leaves the reader oriented, delivered inline in the conversation. Nothing is written, nothing is merged, nothing is judged for defects — this is understanding, and understanding is the whole deliverable.

Guiding idea: **the code already shows the *what*; the value you add is the *why*.** Anyone can read the lines. What's expensive to recover is intent — the decision behind the shape, the alternative that was rejected, the constraint that forced it. Lead with that, and be scrupulously honest about which parts of the "why" you *know* (from a commit, a PR, an issue, an ADR, a comment) versus which you're *inferring* from the code. A confident-sounding invented rationale is the one way this skill actively misleads.

## Core rules

- **Read-only, inline only.** Produce the walkthrough in the conversation. Do not edit code, write files, or post PR/issue comments. If the walkthrough should become durable, hand off to `documentation` — don't write the doc here.
- **Explain the *why*, sourced vs. inferred.** Recover intent from evidence first (commit messages, the PR description, linked issues, ADRs, code comments). State sourced rationale as fact and point to the source; clearly flag anything you infer from the code as inference ("likely…", "appears to…"). Never present a guess as a known decision.
- **Calibrate depth to the target and the ask.** A 30-line helper gets a tight paragraph; a subsystem gets a structured tour. Match the reader's apparent level and what they actually asked — don't pad a small question into an essay.
- **Locate before you read; don't dump the tree.** Find the relevant span with search, read that span, explain it. For a broad section, isolate the survey in a **subagent** so the main thread gets the conclusion, not the whole codebase. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.
- **Links serve digestibility.** Deep-link to the specific thing that helps — a function (`path:line`), the PR/issue that introduced it, the exact page of an official doc, a firm reference under `${CLAUDE_PLUGIN_ROOT}/references/…` when one covers the library. Whatever's most useful, chosen per case; don't manufacture links for ceremony.
- **Write like a human.** Plain, direct, specific. No throat-clearing, no "in this section we will," no restating the code line-by-line. Explain what matters and move on.

## Workflow

### 1. Detect the target & scope
Figure out which of the three you're explaining, because the entry point differs:
- **A file** → read the file (or the relevant spans of a large one).
- **A repo section** (a directory, subsystem, or feature) → map it first — structure, entry points, how the pieces connect — before drilling in. This is the case that most often wants a subagent.
- **A pull request / diff** → get the change and its intent: the diff (`git diff <base>...HEAD`, or the PR via GitHub), the PR description, and any linked issue. If GitHub isn't reachable, fall back to the local diff and say so.

Confirm the scope if it's ambiguous ("the auth module" could mean a file or the whole flow), then scope tightly.

### 2. Gather the *what*
Read enough to explain accurately, not exhaustively. Trace the real path: where data/control enters, what transforms it, where it goes. Note the key types, functions, and boundaries. For a PR, understand not just the changed lines but what they change *about* the behavior — the before and after.

### 3. Reconstruct the *why*
This is the differentiator. Pull intent from evidence in this order, and attribute it:
- **Commit history** for the lines (`git log`/`git blame` on the span) — the message often states the reason.
- **The PR and its linked issue** — the description and discussion are where tradeoffs get argued.
- **ADRs / docs / comments** — a significant decision may already be recorded.
- **Only then, inference from the code itself** — and label it as inference.
If the evidence conflicts or is missing, say so rather than inventing a clean story.

### 4. Assess future considerations
What a reader should carry forward: known risks and sharp edges, TODO/tech-debt markers, coupling that makes change costly, scaling or security concerns visible in the shape (flag them for `code-review`/`security-audit`; don't turn this into a review), and natural next steps the design points toward. Keep it to what's genuinely useful — not a generic checklist.

### 5. Emit the walkthrough
Deliver it inline in the structure below (adapt depth to size — a small target may collapse several sections into a few sentences):

- **TL;DR** — 1–3 sentences a busy reader can stop after: what this is and its role.
- **Walkthrough** — a guided tour of the key pieces in a sensible order (usually the path data/control takes), with `path:line` references so the reader can follow along in the code.
- **Why it's built this way** — the decisions and tradeoffs, each marked sourced (with its source) or inferred.
- **Future considerations** — risks, gotchas, tech debt, and where this naturally goes next.
- **Links** — the handful of references that make it more digestible (code, PR/issue, official docs, firm references).

### 6. Offer to go deeper
Close by pointing at the parts most worth expanding ("want me to drill into the retry logic, or the migration path?") so the reader can pull the thread that matters to them.

## How this works with the other skills
- **onboarding** brings a repo into the firm; **walkthrough** is the on-demand "help me understand *this part*" once you're in it.
- Hand off to **documentation** when a good walkthrough deserves to become durable (a module README, an ADR capturing a decision you surfaced) — walkthrough explains inline, documentation writes the file.
- It complements **code-review**: understand the change with walkthrough, judge it with code-review. Walkthrough *notes* risks; it doesn't rank findings or gate a merge.
- It can front-end **debugging** and **planning** by explaining the affected area first, so the fix or the plan starts from a real mental model.

## What this skill does NOT do
- Edit code, write files, or create anything durable (that's `documentation`).
- Post PR or issue comments — output stays in the conversation.
- Produce a severity-ranked defect review or gate a merge (that's `code-review` / `security-audit`).
- Merge anything.
- Read whole trees when a located span and a subagent survey would do.
