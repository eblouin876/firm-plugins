# OIDC deploy-role module: a GitHub Actions OpenID Connect provider (so CI
# assumes a role via a short-lived web-identity token — NO long-lived AWS
# access keys, per references/security/secrets-management.md) and a
# LEAST-PRIVILEGE deploy role scoped by repo AND branch in its trust policy,
# permitted to do ONLY what a deploy does: push to this ECR repo, roll the
# ECS service, read the provisioned app secrets, and invalidate the
# CloudFront distribution. There is NO `*:*` / admin grant anywhere.

locals {
  oidc_provider_url = "token.actions.githubusercontent.com"
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${var.account_id}:oidc-provider/${local.oidc_provider_url}"

  # Trust is scoped to this repo AND branch — no other repo/branch's workflow
  # can assume the role.
  oidc_sub = "repo:${var.github_repo}:ref:refs/heads/${var.github_branch}"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://${local.oidc_provider_url}"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = var.tags
}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = [local.oidc_sub]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.name_prefix}-deploy"
  assume_role_policy = data.aws_iam_policy_document.trust.json

  tags = var.tags
}

data "aws_iam_policy_document" "deploy" {
  # checkov:skip=CKV_AWS_356:The only "*"-resource statements are ecr:GetAuthorizationToken and ecs:Describe*/RegisterTaskDefinition — AWS does not allow resource-scoping these APIs. Every resource-scopable action (ECR push, ecs:UpdateService, PassRole, CloudFront, S3, Secrets) IS scoped to a specific ARN. There is no wildcard ACTION and no admin grant.
  # ECR auth token: AWS requires "*" resource for GetAuthorizationToken (it
  # is account-scoped, not repo-scoped) — a single specific action, NOT a
  # wildcard action.
  statement {
    sid       = "EcrAuthToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # ECR push/pull scoped to THIS repository only.
  statement {
    sid    = "EcrPushPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [var.ecr_repository_arn]
  }

  # ECS: roll the service. Describe/Register need "*" (they are not
  # resource-scopable) — again specific actions, not a wildcard action.
  statement {
    sid    = "EcsDescribeRegister"
    effect = "Allow"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "EcsUpdateService"
    effect    = "Allow"
    actions   = ["ecs:UpdateService"]
    resources = [var.ecs_service_arn]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
  }

  # PassRole only the two task roles, only to ECS.
  statement {
    sid       = "PassEcsRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [var.task_role_arn, var.execution_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  # CloudFront cache invalidation, scoped to this distribution.
  statement {
    sid       = "CloudFrontInvalidate"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [var.cloudfront_distribution_arn]
  }

  # Static-site sync, scoped to this bucket.
  statement {
    sid       = "StaticSiteList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.static_bucket_arn]
  }

  statement {
    sid    = "StaticSiteObjects"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.static_bucket_arn}/*"]
  }
}

# Read the provisioned app secrets — only added if any exist, scoped to the
# exact ARNs.
data "aws_iam_policy_document" "deploy_secrets" {
  count = length(var.app_secret_arns) > 0 ? 1 : 0

  statement {
    sid       = "ReadProvisionedSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.app_secret_arns
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.name_prefix}-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

resource "aws_iam_role_policy" "deploy_secrets" {
  count = length(var.app_secret_arns) > 0 ? 1 : 0

  name   = "${var.name_prefix}-deploy-secrets"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_secrets[0].json
}
