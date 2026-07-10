---
name: devops
description: Set up and maintain infrastructure, containerization, and CI/CD for a web app — gated deployment, the build/test/deploy pipeline, environment and secrets management, and the operational side (migrations on deploy, observability, rollback). Use this skill WHENEVER the work involves Dockerfiles or Compose, a CI/CD pipeline (GitHub Actions and similar), deployment and hosting, environment/secret configuration, or "how do I ship this / deploy this / containerize this / set up the pipeline / add a deploy gate". Default stack is Docker + GitHub Actions, with the deployment target right-sized to the project — including the Goatenheim home beta server over Tailscale. It detects existing infra and conforms before changing anything, and never applies state-mutating cloud actions without showing the plan and getting confirmation.
---

# DevOps

Get the code that planning scoped and frontend/backend built safely and repeatably to a target, and keep it running. The pipeline is where the other skills' work is enforced automatically: the **test gate** runs the suite the build skills wrote, and the **security gate** automates checks the code-review skill performs by hand. Nothing ships unless the gates pass.

Two principles shape every choice: **containers are the universal artifact** (build once, run identically everywhere), and **right-size the rest** — match orchestration and hosting to the project's actual scale.

## Core rules

- **Detect before you change.** Read existing infra first (Dockerfiles, Compose, CI, deploy target, IaC). Conform; don't impose a toolchain unprompted.
- **Right-size, don't over-engineer.** Docker + Compose for local dev. For production, scale the target to the workload — a PaaS or single host for small apps; managed containers or Kubernetes only when scale/availability justify the operational cost.
- **Gate every deployment.** Lint, type-check, tests, and security scans gate the deploy. Never ship on red.
- **Treat infra changes as dangerous.** Show a plan (dry-run / `terraform plan`) and get explicit confirmation before mutating real infrastructure. Never commit secrets.
- **Work context-efficiently.** Assess infra from the config files, not by reading the whole tree. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Workflow

### 1. Assess current infrastructure (always)
Inspect: containerization (Dockerfiles, Compose, base images), CI/CD (`.github/workflows/`, what's gated, what deploys), deploy target and registry, config/secrets handling (flag anything committed that shouldn't be), IaC, and app shape (web/worker/jobs, backing services, migrations). State what you found and propose in a couple of lines before acting.

### 2. Decide the target (greenfield / open-ended only)
If infra exists, conform. Otherwise pick the tier and say why:
- **Local dev:** Docker + Compose — app + Postgres (+ Redis/worker), one command up.
- **Goatenheim (home beta server):** the default target for personal projects and client previews. Docker on the home box, reachable over **Tailscale**. Deploy by building the image and running it there (Compose or a small deploy step); expose it on the tailnet for you, and to a scoped client via **Tailscale Serve** (tailnet-only) or **Funnel** (authenticated public URL) when they need to see it. Managed Postgres or a persistent volume for data. Great for a beta/staging tier at zero hosting cost.
- **Small production** (freelance app, low traffic): a container PaaS (Fly.io, Render, Railway) or a single managed host — build/deploy/secrets/rollback bundled.
- **Scaling production:** managed container service or Kubernetes, only when requirements justify it.
- CI (build + test + scan gates) lives in GitHub Actions regardless of target.

### 3. Build the pieces
Load the reference for the piece:
- **Containerization** → `${CLAUDE_PLUGIN_ROOT}/references/devops/containers.md`.
- **CI/CD pipeline & gates** → `${CLAUDE_PLUGIN_ROOT}/references/devops/cicd.md`.
- **Deploy & operate** (targets, secrets, migrations on deploy, observability, rollback, IaC) → `${CLAUDE_PLUGIN_ROOT}/references/devops/deploy-operate.md`.

Expectations: dev/prod parity (the image that passed CI is the one that ships); migrations as an explicit ordered deploy step; fail safe with working rollback.

### 4. Agent-testable beta (when relevant)
When a cloud pipeline agent needs to smoke-test the deployed beta: a cloud sandbox is **not** on your tailnet, so it can't reach a Tailscale-only URL directly. Either expose the beta via **Tailscale Funnel with authentication** for the agent to hit, or run the smoke tests **on Goatenheim itself as a self-hosted runner** (already on the tailnet). Pick per sensitivity; keep heavier integration testing on Goatenheim.

### 5. Hand off
Summarize what changed (Dockerfile, compose, workflows, IaC) and how to use it: run locally, what CI gates on, how a deploy is triggered, how to roll back. Call out real-world actions (setting a secret, provisioning) and cost implications. The gate the pipeline enforces is `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`.

## How this works with the other skills
- **planning** can produce an infra plan; this implements it. **frontend/backend** produce the app and tests; this containerizes them and runs the tests as the CI gate; the backend's migrations become a deploy step. **code-review** defines the security standards; this skill's security gate enforces a subset automatically.

## What this skill does NOT do
- Apply infra changes that mutate real cloud resources/state without a shown plan and confirmation.
- Commit secrets or bake them into images.
- Reach for Kubernetes when a simpler target (Goatenheim, a PaaS) meets the requirement.
- Wire a pipeline that deploys when gates fail.
- Write the application code or its tests — it runs and ships them.
