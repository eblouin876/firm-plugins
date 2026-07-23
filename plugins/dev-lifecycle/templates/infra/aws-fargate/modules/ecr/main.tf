# ECR module: one private repository for the app image, encrypted with a
# dedicated KMS key (rotation on), scan-on-push enabled, and IMMUTABLE tags
# so a pushed tag can never be silently overwritten (a deploy always points
# at a fixed, scanned digest). checkov: CKV_AWS_51 (immutable), CKV_AWS_136
# (KMS), CKV_AWS_163 (scan on push).

resource "aws_kms_key" "ecr" {
  description             = "${var.name_prefix} ECR image encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  # Explicit key policy (CKV2_AWS_64): account root retains admin and
  # delegates access control to IAM (the "Enable IAM User Permissions"
  # statement), so principals are granted use via scoped IAM policies rather
  # than editing this key policy.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EnableIAMUserPermissions"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })

  tags = var.tags
}

resource "aws_kms_alias" "ecr" {
  name          = "alias/${var.name_prefix}-ecr"
  target_key_id = aws_kms_key.ecr.key_id
}

resource "aws_ecr_repository" "this" {
  name                 = var.repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.ecr.arn
  }

  tags = var.tags
}

# Expire untagged images so scan noise and storage don't accumulate. Tagged
# images (real releases) are retained.
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = var.untagged_expiry_days
      }
      action = { type = "expire" }
    }]
  })
}
