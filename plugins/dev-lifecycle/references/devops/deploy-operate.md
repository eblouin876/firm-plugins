<!--
library: deployment
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Deploy & operate conventions

Guidance for deployment targets, configuration/secrets, database migrations on deploy, observability, rollback, and infrastructure-as-code. The project's existing setup overrides anything here.

## Contents
- Choosing a deployment target
- Configuration & secrets
- Database & migrations on deploy
- Zero-downtime & rollback
- Observability
- Infrastructure as code

## Choosing a deployment target
Right-size to the workload (don't default to the most powerful option):
- **Single app, low/moderate traffic** (freelance/small SaaS): a container PaaS (Fly.io, Render, Railway) or one managed host. Build/deploy/secrets/rollback/preview envs are largely handled for you. Lowest ops burden.
- **A few services with autoscaling needs:** a managed container service (e.g. cloud "run a container" services, ECS) — more control, still no cluster to babysit.
- **Many services, HA, complex networking:** managed Kubernetes — only when scale (roughly tens of containers across multiple nodes) or availability requirements justify the operational cost.
- Backing services (Postgres, Redis): prefer a **managed** datastore over self-hosting in a container for anything that holds real data — you get backups, failover, and patching. Containers are ephemeral; durable data shouldn't be.

## Configuration & secrets
- **12-factor config:** all config via environment variables; no environment-specific values baked into images.
- **Secrets** live in the platform's secret store or CI secret store, injected at runtime. Never committed, never in images, never logged. Rotate on exposure.
- Keep a documented, non-secret `.env.example` listing required variables so a new environment is reproducible.
- Separate config per environment (dev/staging/prod); least privilege for each environment's credentials.

## Database & migrations on deploy
- Migrations are an explicit deploy step, ordered relative to the release. Follow the backend skill's Alembic conventions.
- **Sequence expand/contract for zero-downtime:** additive, backward-compatible migrations first (add nullable column/table), deploy code that works with both shapes, backfill, then a later migration tightens constraints / removes the old shape. Avoid a single migration that breaks the currently-running version.
- Back up / snapshot before destructive or risky migrations. Have a tested restore path.
- Never auto-create schema (`create_all`) in production; migrations are the source of truth.

## Zero-downtime & rollback
- Use the target's rolling/blue-green/canary mechanism; gate cutover on health checks.
- **Rollback plan is part of every deploy:** redeploy the previous image SHA to revert code instantly. For data/migrations, know in advance whether a change is reversible and how — code rollback doesn't undo a destructive migration.
- Drain connections on shutdown (handle SIGTERM) so rollouts don't drop in-flight requests.

## Observability
You can't operate what you can't see. Establish, scaled to the project:
- **Logs:** structured (JSON) to stdout/stderr, aggregated by the platform; never log secrets/PII.
- **Metrics:** request rate, error rate, latency (the RED signals) and resource use; dashboards for the key ones.
- **Tracing:** for multi-service paths, distributed tracing (OpenTelemetry) to follow a request across boundaries.
- **Error tracking:** an exception tracker (e.g. Sentry) for app errors with context.
- **Alerting:** alert on symptoms users feel (elevated error rate, latency, availability) and on security-relevant events (auth failures, access-control denials — ties to OWASP A09). Avoid alert noise; page on what needs action.
- **Health endpoints:** liveness/readiness so the platform routes traffic only to healthy instances.

## Infrastructure as code
- Define provisioned infrastructure declaratively (Terraform/Pulumi/OpenTofu or the platform's config) and keep it in version control. No click-ops snowflakes.
- **Always review the plan before applying.** `terraform plan` (or equivalent dry-run) shows what will change; confirm before `apply`, especially for anything that destroys/replaces resources or touches state. This is where outages and data loss happen — treat it with care and surface it to the user for explicit sign-off.
- Manage state safely (remote, locked backend); never commit state files or secrets.
- Keep environments parameterized from the same definitions so staging mirrors production.
