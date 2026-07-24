---
name: "technical-proposal"
description: "Produce a technical proposal for building something — the recommended stack and why, the high-level architecture, and an honest cost/timeline estimate — so a build/no-build decision can be made before any code or roadmap. Use this skill WHENEVER the question is whether and how to build a system: \"what stack should we use for X\", \"propose an architecture for this\", \"what would it take to build Y\", \"is this worth building\", \"scope the tech for this idea\". This is the internal/architecture proposal that opens a greenfield and feeds product-planning. For a persuasive CLIENT-facing sales pitch of a website build, use the web-proposal-writer skill instead; this one is the engineering decision doc."
---

# Technical proposal

Decide whether and how to build something, on paper, before committing. The proposal does three jobs: **recommend** a stack and architecture, **justify** them for *this* problem (not generically), and **estimate** what it will cost and take. It's a decision artifact — no implementation, no repo yet. For a greenfield product it's the first step; its output feeds `product-planning`, which turns the approved direction into a staged roadmap.

## Core rules

- **Recommend, justify, cost — all three.** A stack list with no rationale is useless; a rationale with no cost is half a decision. Cover what, why, and what it'll take.
- **Justify for the specific problem.** Tie every choice to this system's actual needs — scale, interactivity, team, integrations, timeline. Default to the firm's stacks (Python back / TypeScript front) but *earn* them for the case; don't cargo-cult, and don't over-engineer (no Kubernetes/microservices for a CRUD app).
- **Ground in current reality.** Version and ecosystem facts come from the reference library or current official docs, not recall — the stack you recommend should reflect what's actually current and supported.
- **Never fabricate numbers.** Cost and timeline are honest ranges with stated assumptions. If an input needed to estimate is missing (scale, team size, budget), ask or state the assumption — a made-up number is worse than a flagged gap. This is an estimate, not a quote.
- **It's a decision doc, not a build.** No code, no scaffolding, no repo. The decision is the user's; the proposal informs it.
- **Work context-efficiently.** For a brownfield addition, assess the existing system from manifests and a few representative files, not the whole tree. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Workflow

### 1. Understand the problem & constraints
What's being built and for whom; the core capabilities; scale expectations (users, data, traffic); hard constraints (budget, deadline, compliance, existing systems to integrate); and the team that'll run it. Ask for the few inputs that actually change the recommendation; assume-and-state the rest.

### 2. Recommend the stack & architecture
Propose the stack (backend, frontend, datastore, hosting) and a high-level architecture. For each significant choice, give the rationale and the main **alternative considered and why it was rejected**. Default to firm stacks where they fit; justify a departure where they don't. Right-size to the real scale. Reference the backend/frontend library docs for what's current.

### 3. Estimate cost & timeline
Break the build into areas (backend, frontend, infra, integrations) and give an effort estimate as a **range with assumptions**. Include running/hosting cost (e.g. a PaaS vs a home-server beta vs cloud). State clearly what would move the number.

### 4. Assess risks & open questions
The things that could change the plan: technical unknowns, integration risks, scale cliffs, decisions that need the user's input.

### 5. Produce the proposal
Write a markdown proposal: problem & goals → recommended stack & architecture (with rationale and alternatives) → cost/timeline estimate → risks & open questions → recommendation. The architecture decisions map cleanly onto an ADR (`documentation` skill) once accepted. If this turns out to be a client sales pitch rather than an engineering decision, hand to `web-proposal-writer` instead.

### 6. Hand off
Present the recommendation and the decision it enables. For a greenfield that's a go, the next move is `product-planning` (north star + staged roadmap) → `scaffolding` (create & init the repo) → `planning` per stage.

## What this skill does NOT do
- Fabricate costs, timelines, or metrics — estimate honestly with assumptions, or ask.
- Write implementation code, scaffold, or create a repo.
- Produce a persuasive client sales proposal (that's `web-proposal-writer`).
- Over-engineer the recommendation beyond the problem's real scale.
