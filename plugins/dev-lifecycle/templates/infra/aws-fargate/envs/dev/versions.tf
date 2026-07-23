# Terraform + provider version constraints for the dev environment root.
#
# Versions are governed by references/compatibility-matrix.md (Infra row) —
# Terraform core ~> 1.15 and hashicorp/aws ~> 6.55 — not restated as literal
# numbers scattered through the config. See this block's README
# `versions-pinned-to`. `hashicorp/random` backs the RDS module's generated
# master password (Option A); no version-sensitive behavior, floored loosely.
#
# Commit `.terraform.lock.hcl` in a real project so provider patch versions
# are reproducible across machines and CI (references/infra/terraform.md,
# "Provider version pinning"). This template ships no lockfile — a fresh
# `terraform init` resolves it against the matrix on first use.

terraform {
  required_version = "~> 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.55"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
