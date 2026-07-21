<!--
library: terraform
versions-covered: "Terraform core ~> 1.15, hashicorp/aws provider ~> 6.x"
last-verified: 2026-07-21
provenance: manual
sources:
  - https://developer.hashicorp.com/terraform/enterprise/releases
  - https://registry.terraform.io/providers/hashicorp/aws/latest
  - https://developer.hashicorp.com/terraform/language/state/locking
  - https://developer.hashicorp.com/terraform/cli/workspaces
  - https://aquasecurity.github.io/tfsec/
  - https://www.checkov.io/
-->

# Terraform conventions

How the kit uses Terraform to provision AWS ECS Fargate infra (per epic #22). Read after choosing the infra block. Subordinate to the project's existing conventions — when they conflict, the project wins.

## Contents
- Version check (do this first)
- Module structure
- Remote state + locking
- Workspaces / environments
- Provider version pinning
- Least privilege, no static keys
- Plan before apply
- Static analysis (tfsec / checkov)

## Version check (do this first)
Two independently-versioned pieces:
- **Terraform core:** pin `~> 1.15` (current stable line; `1.16` exists only as an alpha — do not adopt pre-GA). Set in a `required_version` constraint, not just CI tooling.
- **`hashicorp/aws` provider:** pin `~> 6.x` (current major, `6.55.x` as of this pin). Provider majors carry breaking resource/attribute changes — read the version's upgrade guide before bumping the major, never as a drive-by. Both lines are governed by `references/compatibility-matrix.md`; re-verify there before changing either.

## Module structure
- Root modules per deployable unit (e.g. `infra/envs/<env>/`), composed from reusable modules under `infra/modules/<name>/` (network, ecs-service, rds, etc.).
- Each module: `main.tf`, `variables.tf`, `outputs.tf`, and a short `README.md` stating its inputs/outputs — same discipline as a template block's composition contract.
- No environment-specific values hardcoded inside a shared module; environments supply them via variables.

## Remote state + locking
- State lives in a remote backend (S3) with **native S3 state locking**: `use_lockfile = true` in the `s3` backend block (stable since Terraform 1.11, uses S3 conditional writes) — no separate DynamoDB lock table needed on current core. Never commit `.tfstate`, never share state via local files.
- One state file per environment (see Workspaces below) so a mistake in staging can't touch prod's state.
- Enable S3 bucket versioning on the state bucket so a bad apply's prior state is recoverable.

## Workspaces / environments
- Prefer **directory-per-environment** (`infra/envs/dev`, `infra/envs/staging`, `infra/envs/prod`) over native Terraform workspaces for anything prod-bound — it keeps state isolation explicit and lets environments diverge (instance sizes, replica counts) without conditional logic sprawl.
- Native `terraform workspace` is acceptable for short-lived, throwaway environments (a PR preview stack) where full directory duplication is overkill.

## Provider version pinning
- Pin every provider in a `required_providers` block with a `~>` floor tied to the matrix; commit `.terraform.lock.hcl` so provider patch versions are reproducible across machines and CI.
- Cross-link `references/compatibility-matrix.md` — that table, not this file, is the source of truth for the exact pinned line.

## Least privilege, no static keys
- CI and any human/automation running `plan`/`apply` authenticate via **GitHub OIDC → an assumed IAM role**, never long-lived AWS access keys. See `references/security/secrets-management.md` for the OIDC setup.
- Scope the deploy role's IAM policy to the resources this stack actually manages — no `*:*` admin roles for CI.
- This is the same posture `references/infra/aws.md` and `references/security/secure-baseline.md` require kit-wide; Terraform is the enforcement point for IAM, not an exception to it.

## Plan before apply
- **Always run `terraform plan` and review it before `terraform apply`** — especially for anything showing a replace or destroy. This applies in CI too: `plan` on every PR touching `infra/`, gate `apply` behind a merge to the environment's branch (or manual approval for prod).
- Treat an unreviewed `apply` (local, against a shared environment) as an incident waiting to happen — always target a named workspace/environment explicitly (`-target` sparingly, never as a routine crutch).

## Static analysis (tfsec / checkov)
- Run **tfsec** and/or **checkov** in CI against every `infra/` change, alongside `terraform validate` and `fmt -check`. Fail the check on high-severity findings (open security groups, unencrypted storage, public S3 buckets, overly broad IAM).
- Treat a suppressed finding as a documented exception (inline comment with reason), not a silent skip.
