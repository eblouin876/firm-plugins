<!--
block: infra/aws-fargate
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
needs:
  - a built + pushed app container image (backend/fastapi or backend/django prod target) in the provisioned ECR repo; the app reads DATABASE_URL/JWT_SIGNING_KEY/SMTP_* from process env (secret_store.py, process-env-first)
  - AWS account + credentials for `apply` only (via GitHub OIDC — the provisioned deploy role); ACM cert ARN(s) for the ALB (regional) and, optionally, CloudFront (us-east-1)
  - Terraform ~> 1.15, hashicorp/aws ~> 6.55 (versions-pinned-to), an S3 state bucket (native lockfile, no DynamoDB)
exposes:
  - a running ECS Fargate service behind an HTTPS ALB; a CloudFront-fronted private static-site bucket; an encrypted private RDS Postgres; app secrets in Secrets Manager (DATABASE_URL/JWT_SIGNING_KEY/SMTP_*); a least-privilege GitHub-OIDC deploy role
  - contract outputs: ecr_repository_url, ecs_cluster_name, ecs_service_name, alb_dns_name, cloudfront_domain_name, cloudfront_distribution_id, app_secret_arns, deploy_role_arn
  - its co-located doc fragment: docs/fragment.md (Deployment + Secrets + Maintenance)
-->

# infra/aws-fargate

The secure-by-default AWS ECS Fargate infrastructure block: a directory-per-
environment Terraform root (`envs/dev/`) composed from seven reusable modules
(`modules/`). It provisions the whole runtime for a monorepo app — network,
container registry, secrets, database, static site, the Fargate service behind
an HTTPS ALB, and a keyless GitHub-OIDC deploy role. Lives at
`templates/infra/aws-fargate/` in this repo; scaffolding materializes it into a
project's `infra/aws-fargate/`. Everything here is a default a scaffolded
project can and will diverge from — when a project has already diverged, the
project wins.

## Contents
- Composition contract
- Structure
- Directory-per-environment + remote state
- Credential-free verification (validate / plan, never apply)
- Security posture (secure-by-default)
- checkov: satisfied-by-design + the documented skips
- Documentation

## Composition contract

### NEEDS
- **A built + pushed app image** in the provisioned ECR repository — the
  hardened PROD target of `backend/fastapi/Dockerfile` or
  `backend/django/Dockerfile` (non-root, no `--reload`, `HEALTHCHECK`). The
  running container reads `DATABASE_URL`, `JWT_SIGNING_KEY`, and `SMTP_*` from
  process env; this block injects each via the ECS task's `secrets`/`valueFrom`
  mapping, so the app fetches nothing.
- **AWS credentials for `apply` only** — via GitHub OIDC (the `deploy_role_arn`
  this block provisions), never long-lived keys. `validate`/`plan` need no
  credentials (see "Credential-free verification").
- **ACM certificate ARN(s)** — one in this region for the ALB HTTPS listener
  (required); optionally one in us-east-1 for a CloudFront custom domain.
- **An S3 state bucket** — native S3 lockfile (`use_lockfile = true`), no
  DynamoDB lock table (Terraform ~> 1.15). Supplied at `init` via
  `-backend-config`.
- **Terraform ~> 1.15, hashicorp/aws ~> 6.55** — per
  `references/compatibility-matrix.md` (Infra row); not restated in `.tf`.

### EXPOSES
- **A running stack**: ECS Fargate service behind an HTTPS ALB (HTTP->HTTPS
  redirect), a CloudFront-fronted private static-site bucket, an encrypted
  private RDS Postgres, the app secrets in Secrets Manager, and a
  least-privilege GitHub-OIDC deploy role.
- **Contract outputs** (root): `ecr_repository_url`, `ecs_cluster_name`,
  `ecs_service_name`, `alb_dns_name`, `cloudfront_domain_name`,
  `cloudfront_distribution_id`, `app_secret_arns`, `deploy_role_arn`.
- **Its co-located doc fragment**: `docs/fragment.md` (Deployment runbook +
  Secrets rows + Maintenance), aggregated into the root README by
  `just docs-generate`.

### Inputs (root)
`aws_region`, `account_id` (a **variable**, not an `aws_caller_identity`
lookup, so plan runs offline), `project_name`, `environment`, networking
(`vpc_cidr`, `az_count`), the app image (`app_image_tag`, `container_port`,
`app_environment`, `desired_count`, `task_cpu`, `task_memory`,
`health_check_path`), the database (`db_url_scheme` — `postgresql+asyncpg` for
FastAPI vs `postgresql` for Django — `db_name`, `db_username`,
`db_instance_class`, `db_allocated_storage`, `db_engine_version`), TLS
(`alb_acm_certificate_arn`, `cloudfront_acm_certificate_arn`,
`cloudfront_aliases`), and CI/OIDC (`github_repo`, `github_branch`,
`create_oidc_provider`). See `envs/dev/terraform.tfvars.example`.

## Structure

```
templates/infra/aws-fargate/
  envs/dev/                     # the dev environment root (copy for staging/prod)
    main.tf                      # provider (skip_* offline flags) + module composition
    variables.tf                 # all inputs (account_id is a variable, not a data source)
    outputs.tf                   # the contract outputs
    versions.tf                  # required_version ~> 1.15, aws ~> 6.55, random
    backend.tf                   # S3 backend, use_lockfile (no DynamoDB)
    terraform.tfvars.example      # placeholder values (also the offline-plan var-file)
  modules/
    network/                     # VPC, public+private subnets, IGW, NAT, routes, flow logs, default-SG lockdown
    ecr/                         # scan-on-push, immutable, KMS
    secrets/                     # Secrets Manager (JWT + SMTP) + KMS (rotation)
    rds/                         # encrypted private Postgres, force_ssl, composed DATABASE_URL (Option A)
    static-site/                 # private S3 + OAC CloudFront + security headers + TLS 1.2
    ecs-fargate-service/         # cluster, hardened task def (valueFrom secrets), ALB HTTPS, scoped SGs
    oidc-deploy-role/            # GitHub OIDC provider + least-privilege deploy role
  scripts/deploy.sh             # the `just deploy` entrypoint (OIDC assume -> push -> deploy)
  docs/fragment.md              # co-located doc fragment (Deployment/Secrets/Maintenance)
```

## Directory-per-environment + remote state

Each environment is its own root under `envs/<env>/` (state isolation is
explicit; environments diverge via their own `tfvars`, not conditional logic).
State lives in S3 with **native lockfile locking** (`use_lockfile = true`,
Terraform ~> 1.15) — **no DynamoDB lock table**. (The DynamoDB lock table is
the pre-1.11 fallback; a project pinned below 1.11 would add a `dynamodb_table`
to `backend.tf`, but this kit targets ~> 1.15.) See
`references/infra/terraform.md`.

## Credential-free verification (validate / plan, never apply)

The provider sets `skip_credentials_validation`, `skip_requesting_account_id`,
and `skip_metadata_api_check`, and the config uses **no plan-time API-call data
sources** (`account_id` is a variable; AZ names are derived from the region).
So the full verification runs with no real credentials and no cloud calls:

```
terraform fmt -check -recursive
terraform init -backend=false            # or with -plugin-dir for an offline mirror
terraform validate
terraform plan -var-file=terraform.tfvars.example   # dummy creds env, no state, no apply
checkov --directory . --framework terraform          # exit 0
```

There is **no `terraform apply`** in verification — plan only. `apply` happens
in CI, authenticated via the provisioned OIDC deploy role.

## Security posture (secure-by-default)

- **Secrets via `valueFrom`, never in env or image.** Each Secrets Manager ARN
  maps to the exact env var the app reads (`DATABASE_URL`, `JWT_SIGNING_KEY`,
  `SMTP_USERNAME`, `SMTP_PASSWORD`) through the task definition's `secrets`
  block. Nothing sensitive is in the task `environment` or baked into the
  image.
- **Encryption everywhere at rest** — RDS (dedicated CMK), ECR (CMK), Secrets
  Manager (CMK, rotation on), CloudWatch log groups (CMK), S3 (SSE). RDS also
  forces **TLS in transit** (`rds.force_ssl`); the composed `DATABASE_URL`
  carries the driver-correct SSL param.
- **Private data tier** — RDS not publicly accessible, in private subnets; the
  static-site bucket blocks all public access and is reachable only through
  CloudFront (OAC).
- **Tight security groups** — RDS 5432 from the ECS task SG only; ECS from the
  ALB SG only; the ALB public on 80/443 (its job), redirecting 80->443. The
  VPC default SG is locked down.
- **Keyless CI** — GitHub OIDC provider + a least-privilege deploy role scoped
  by repo/branch, permitted only to push to ECR / roll the ECS service /
  GetSecretValue on the provisioned ARNs / invalidate CloudFront / sync the
  static bucket. **No `*:*`.**

This block clears the `template-author` four bars: composition-contract
(above), documented (`docs/fragment.md` + this README), version-pinned
(`versions-pinned-to` -> compatibility matrix), and secure-by-default (this
section, verified `checkov` exit 0).

## checkov: satisfied-by-design + the documented skips

`checkov==3.2.526 --directory . --framework terraform` exits **0**. The
security posture above satisfies the checks by design; every remaining finding
is an inline `# checkov:skip=<ID>:<reason>` (never a silent skip), each an
opt-in-for-a-starter item:

| Check | Where | Why skipped |
| --- | --- | --- |
| `CKV2_AWS_57` | secrets, rds | App-managed secrets (signing key, relay creds, composed DB URL) have no AWS-native rotation Lambda; rotation is manual per `secrets-management.md`. |
| `CKV_AWS_157` | rds | RDS Multi-AZ is opt-in (cost) — `var.multi_az = true` for prod HA. |
| `CKV_AWS_260` | ecs (ALB SG) | Public :80 ingress is the ALB's purpose; the listener only 301-redirects to HTTPS; the app tier is private. |
| `CKV_AWS_356` | oidc | The only `*`-resource statements are `ecr:GetAuthorizationToken` / `ecs:Describe*`/`RegisterTaskDefinition`, which AWS cannot resource-scope; every scopable action IS scoped. No wildcard action. |
| `CKV_AWS_18`, `CKV_AWS_86`, `CKV_AWS_91` | static-site, ecs (ALB) | Access logging to a dedicated log bucket is opt-in. |
| `CKV_AWS_68`, `CKV2_AWS_47`, `CKV2_AWS_28` | static-site, ecs | WAF (WebACL) is opt-in for a starter. |
| `CKV_AWS_144` | static-site | Cross-region replication is opt-in (assets are redeployable). |
| `CKV_AWS_145` | static-site | Public web assets; SSE-S3 satisfies at-rest — switch to SSE-KMS if the bucket holds sensitive objects. |
| `CKV_AWS_174`, `CKV2_AWS_42` | static-site | Default `*.cloudfront.net` cert for a domain-less starter; set `cloudfront_acm_certificate_arn` for a custom domain pinned to TLSv1.2_2021. |
| `CKV_AWS_310` | static-site | Origin failover is opt-in (single origin). |
| `CKV_AWS_374` | static-site | Global public site — geo restriction "none" by design. |
| `CKV2_AWS_62` | static-site | S3 event notifications are opt-in (no event consumer). |

## Documentation

Ships `docs/fragment.md` co-located with the block; `just docs-generate`
aggregates its `## Deployment` / `## Secrets` / `## Maintenance` sections into
the project root README. See
`references/authoring/documentation-standard.md`.
