---
name: infrastructure
description: Provision and maintain the infrastructure that apps run on — cloud (AWS via IaC), a home/beta server (Goatenheim), or a VPS — and keep it healthy over time: networking (Tailscale), backups, monitoring, updates/patching, TLS, access control, and resilience/auto-recovery. Use this skill WHENEVER the work is about the hosting environment rather than the app itself: "set up the server", "provision AWS for this", "configure the home box", "set up Tailscale", "add backups/monitoring", "make sure it comes back after a reboot", "why is the host unreachable", "harden this infrastructure". It detects existing infra and conforms, and never mutates real infrastructure without showing a plan and getting confirmation. This is the ops/maintenance counterpart to devops, which ships the app.

---

# Infrastructure

Stand up the places apps run, and keep them alive. Where `devops` gets the app *shipped* (containerize, CI, deploy), this skill owns the *environment* — provisioning it, wiring its networking, and maintaining it over time: backups, monitoring, patching, TLS, access, and the resilience that makes a host recover on its own. It's the ops half of the firm.

## Core rules

- **Detect before you change, and treat mutations as dangerous.** Read the existing infra first. Anything that provisions, destroys, or mutates real state gets a **plan/dry-run shown and explicit confirmation** before it's applied — this is where outages and data loss happen. Never commit secrets.
- **Reproducible, not snowflake.** Cloud infra is defined as code (Terraform/OpenTofu/Pulumi/CDK) in version control; host setup is scripted or documented. No undocumented manual changes that can't be recreated.
- **Right-size to scale and budget.** A beta/personal service on **Goatenheim** or a small VPS; a PaaS or managed cloud when the workload justifies it; managed data stores over self-hosting anything durable. Don't provision a cloud estate for a side project.
- **Resilience is designed in.** Backups with a *tested restore path*, monitoring/alerting on what users feel, and recovery so a host comes back on its own after a reboot or power loss (see `${CLAUDE_PLUGIN_ROOT}/references/infra/home-infra.md`).
- **Least privilege everywhere.** Cloud IAM, host users, and Tailscale ACLs all scoped to what's needed; no long-lived keys where a role/OIDC works.
- **Work context-efficiently.** Assess from IaC/config and status commands, not by exploring everything. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.

## Workflow

### 1. Assess current infrastructure
What exists: cloud resources and IaC, hosts (Goatenheim/VPS), the tailnet, backups, monitoring, TLS, secrets handling. State findings and what you propose before touching anything.

### 2. Choose / right-size the target
Load the reference for the target:
- **Cloud (AWS)** → `${CLAUDE_PLUGIN_ROOT}/references/infra/aws.md`.
- **Home / beta server (Goatenheim)** → `${CLAUDE_PLUGIN_ROOT}/references/infra/home-infra.md`.
- **Networking / access (Tailscale)** → `${CLAUDE_PLUGIN_ROOT}/references/infra/tailscale.md`.
For deploying an app onto provisioned infra, hand back to `${CLAUDE_PLUGIN_ROOT}/references/devops/deploy-operate.md`.

### 3. Provision / configure
Cloud: write/adjust IaC, run the plan, **show it, confirm, then apply**. Hosts: scripted, documented setup. Networking: wire the tailnet (ACLs, MagicDNS, Serve/Funnel, subnet routes, key-expiry) per the Tailscale reference.

### 4. Harden & make resilient
Backups with a tested restore; monitoring and alerting on the signals users feel (availability, errors, latency) and on host health (disk, memory, cert expiry); an updates/patching cadence; TLS/certs with auto-renewal; and recovery — services auto-restart, and hosts auto-boot after power loss (home-infra reference).

### 5. Hand off
Summarize what was provisioned/changed and how to operate it: run, back up, restore, monitor, and roll back. Call out real-world actions (a DNS change, a secret to set, a BIOS setting) and cost implications, and state the recovery behavior (what happens on reboot / power loss / a hung service).

## What this skill does NOT do
- Mutate real cloud/infra state without a shown plan and explicit confirmation.
- Commit secrets, or make undocumented snowflake changes.
- Over-provision beyond the workload's real need.
- Ship application code or its CI/CD — that's `devops`; this provides the environment devops deploys into.
