# Remote state backend for the dev environment.
#
# Native S3 state locking (`use_lockfile = true`, stable since Terraform
# 1.11 via S3 conditional writes) — NO DynamoDB lock table on current core
# (references/infra/terraform.md, "Remote state + locking"). The pre-1.11
# fallback was a `dynamodb_table` lock table; a project pinned below 1.11
# would add that here instead, but this kit targets ~> 1.15, so the
# lockfile is the mechanism.
#
# Partial configuration: bucket / key / region are supplied at init time so
# the same root serves multiple environments without hardcoding a
# per-environment bucket here —
#
#   terraform init \
#     -backend-config="bucket=<your-tf-state-bucket>" \
#     -backend-config="key=aws-fargate/dev/terraform.tfstate" \
#     -backend-config="region=<your-region>"
#
# Enable versioning on the state bucket (recoverable prior state) and block
# all public access on it — it holds state, which can contain sensitive
# values. Offline verification runs `terraform init -backend=false`, which
# skips this block entirely (no bucket, no credentials, no network).

terraform {
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
