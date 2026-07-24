<!--
library: aws
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://docs.aws.amazon.com
-->

# AWS conventions

Provisioning and running a web app on AWS, right-sized. Read after choosing the AWS target. Existing infra/IaC overrides anything here. Confirm current service details against the AWS docs — the console and service defaults change.

## Infrastructure as code first
- Define everything as code (Terraform/OpenTofu, Pulumi, or CDK) in version control — no click-ops snowflakes.
- **Always review the plan before applying.** `terraform plan` (or the equivalent) shows what changes; confirm before `apply`, especially for anything that replaces or destroys resources or touches state. Manage state in a remote, locked backend; never commit state or secrets.

## Right-sizing (don't over-build)
Match the target to the workload:
- **Small app / low traffic:** a container PaaS-style service — **App Runner** or **Lightsail Containers** — or **ECS Fargate**. No cluster to babysit.
- **A few services / autoscaling:** **ECS Fargate** behind an ALB.
- **Kubernetes (EKS):** only when scale, multi-team, or ecosystem needs genuinely justify the operational cost.
- Don't stand up a sprawling multi-AZ VPC and EKS for a side project.

## Core services for a web app
- **Compute:** App Runner / Lightsail / ECS Fargate (per above).
- **Data:** **RDS (Postgres) — managed**, not self-hosted on EC2. Managed backups, failover, patching. See `${CLAUDE_PLUGIN_ROOT}/references/backend/postgres.md`.
- **Storage:** S3 (private by default; never public buckets unless explicitly intended).
- **Registry:** ECR for images.
- **Networking:** VPC with private subnets for data, an ALB for ingress; security groups scoped tight.
- **DNS/TLS:** Route 53 + ACM (managed certs, auto-renewed).
- **Secrets/config:** Secrets Manager or SSM Parameter Store, injected at runtime — never baked into images or committed.
- **CDN:** CloudFront for static assets / edge caching where it helps.

## Security
- **Least-privilege IAM.** Scope roles to what a task needs; no wildcard admin. Use **OIDC/roles** for CI and workloads — **no long-lived access keys** where a role works.
- Private subnets for databases; nothing public that doesn't need to be. Encryption at rest and in transit on by default.
- Turn on baseline guardrails (CloudTrail logging, GuardDuty where warranted); no default-open security groups.

## Cost
- Watch the usual bill-drivers: NAT gateways, idle load balancers, oversized/always-on RDS, and inter-AZ / egress data transfer.
- **Tag resources** by project/env; set **budgets and cost alerts** so a surprise is caught early. Tear down what a beta no longer needs — this is where a home server (zero hosting cost) often wins for beta/staging.
