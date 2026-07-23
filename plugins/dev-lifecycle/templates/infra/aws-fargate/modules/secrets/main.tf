# Secrets module: a dedicated KMS key (rotation on) plus the app's
# Secrets Manager entries. Secrets are injected into the ECS task via
# `secrets`/`valueFrom` (ecs-fargate-service module) mapping each ARN to the
# exact env var the app reads process-env-first (secret_store.py) — NEVER
# placed in the task `environment` block or baked into the image.
#
# JWT_SIGNING_KEY is generated here (random_password) so a strong value
# exists at provision time. SMTP creds come from an external relay, so their
# secret containers are created with a placeholder version the operator
# overwrites out-of-band (lifecycle ignore_changes on the value) — Terraform
# provisions the container and grants, not the live credential.
#
# The DATABASE_URL secret is NOT created here — the rds module composes and
# stores it (Option A) using this module's KMS key, since only rds knows the
# generated master password, host, and port. This module exposes kms_key_arn
# for that.

resource "aws_kms_key" "secrets" {
  description             = "${var.name_prefix} application secrets encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  # Custom key policy: account root retains full admin AND (the "Enable IAM
  # User Permissions" statement) delegates access control to IAM, so the ECS
  # execution role and the deploy role can be granted kms:Decrypt via their
  # own scoped IAM policies (ecs/oidc modules) rather than editing this
  # policy. Secrets Manager is additionally allowed via its ViaService
  # condition.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableIAMUserPermissions"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
    ]
  })

  tags = var.tags
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name_prefix}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# --- JWT_SIGNING_KEY (generated) --------------------------------------------

resource "random_password" "jwt_signing_key" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt_signing_key" {
  name        = "${var.name_prefix}/JWT_SIGNING_KEY"
  description = "HS256 JWT signing key for the backend auth component (JWT_SIGNING_KEY)."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = var.recovery_window_in_days

  # checkov:skip=CKV2_AWS_57:App-managed signing key — no AWS-native rotation Lambda applies. Rotation is manual on suspected exposure or on a token-invalidation-window plan (references/security/secrets-management.md, "Rotation").
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "jwt_signing_key" {
  secret_id     = aws_secretsmanager_secret.jwt_signing_key.id
  secret_string = random_password.jwt_signing_key.result
}

# --- SMTP credentials (operator-supplied) -----------------------------------

resource "aws_secretsmanager_secret" "smtp_username" {
  count = var.manage_smtp_secrets ? 1 : 0

  name        = "${var.name_prefix}/SMTP_USERNAME"
  description = "SMTP relay username for outbound email (SMTP_USERNAME)."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = var.recovery_window_in_days

  # checkov:skip=CKV2_AWS_57:External relay credential — no AWS-native rotation Lambda. Rotate on the relay's schedule / on exposure (references/security/secrets-management.md).
  tags = var.tags
}

resource "aws_secretsmanager_secret" "smtp_password" {
  count = var.manage_smtp_secrets ? 1 : 0

  name        = "${var.name_prefix}/SMTP_PASSWORD"
  description = "SMTP relay password for outbound email (SMTP_PASSWORD)."
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = var.recovery_window_in_days

  # checkov:skip=CKV2_AWS_57:External relay credential — no AWS-native rotation Lambda. Rotate on the relay's schedule / on exposure (references/security/secrets-management.md).
  tags = var.tags
}

# Placeholder initial versions; the operator overwrites the value out-of-band
# (console/CLI). ignore_changes keeps Terraform from reverting the real value
# on the next apply — Terraform owns the container + grants, not the live
# credential.
resource "aws_secretsmanager_secret_version" "smtp_username" {
  count = var.manage_smtp_secrets ? 1 : 0

  secret_id     = aws_secretsmanager_secret.smtp_username[0].id
  secret_string = "REPLACE_ME_SET_OUT_OF_BAND"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret_version" "smtp_password" {
  count = var.manage_smtp_secrets ? 1 : 0

  secret_id     = aws_secretsmanager_secret.smtp_password[0].id
  secret_string = "REPLACE_ME_SET_OUT_OF_BAND"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
