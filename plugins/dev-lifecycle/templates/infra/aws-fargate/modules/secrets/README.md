<!--
module: secrets
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# secrets module

A dedicated KMS key (rotation on) plus the app's Secrets Manager entries.
Secrets are injected into the ECS task via `secrets`/`valueFrom` (the
ecs-fargate-service module), NEVER placed in the task `environment` or baked
into the image. The app reads each by name, process-env-first
(`secret_store.py`).

- **`JWT_SIGNING_KEY`** — generated here (`random_password`), so a strong value
  exists at provision time.
- **`SMTP_USERNAME` / `SMTP_PASSWORD`** — created as containers with a
  placeholder version the operator overwrites out-of-band
  (`ignore_changes` on the value); Terraform owns the container + grants, not
  the live credential. Disable with `manage_smtp_secrets = false`.
- **`DATABASE_URL`** is NOT created here — the rds module composes and stores
  it (Option A) using this module's `kms_key_arn`.

Secret rotation is manual per `references/security/secrets-management.md`
(no AWS-native rotation Lambda applies to a signing key or relay creds) —
`CKV2_AWS_57` is skipped inline with that justification.

## Inputs
| Name | Description |
| --- | --- |
| `name_prefix` | Resource name prefix / Secrets Manager path prefix. |
| `account_id` | AWS account ID (scopes the KMS key policy). |
| `manage_smtp_secrets` | Create SMTP_* secret containers (default true). |
| `recovery_window_in_days` | Secrets Manager recovery window (default 7). |
| `tags` | Tags applied to every resource. |

## Outputs
| Name | Description |
| --- | --- |
| `kms_key_arn` | App-secrets KMS key ARN (also used by rds for DATABASE_URL). |
| `app_secret_arns` | Map of env var name -> Secrets Manager ARN. |
