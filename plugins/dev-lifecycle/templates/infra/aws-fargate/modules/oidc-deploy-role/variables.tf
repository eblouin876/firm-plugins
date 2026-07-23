variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Used to construct the OIDC provider ARN offline when create_oidc_provider is false (no data source, so plan stays offline)."
  type        = string
}

variable "aws_region" {
  description = "AWS region (scopes ECS ARNs in the deploy policy)."
  type        = string
}

variable "github_repo" {
  description = "GitHub repo the deploy role trusts, 'owner/name'."
  type        = string
}

variable "github_branch" {
  description = "Git branch whose workflows may assume the role (OIDC `sub` is scoped to refs/heads/<branch>)."
  type        = string
  default     = "main"
}

variable "create_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. False if the account already has one."
  type        = bool
  default     = true
}

variable "ecr_repository_arn" {
  description = "ECR repository ARN the deploy role may push to."
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ECS cluster ARN (scopes the UpdateService condition)."
  type        = string
}

variable "ecs_service_arn" {
  description = "ECS service ARN the deploy role may update."
  type        = string
}

variable "task_role_arn" {
  description = "Task role ARN — deploy role may iam:PassRole it (for RegisterTaskDefinition)."
  type        = string
}

variable "execution_role_arn" {
  description = "Execution role ARN — deploy role may iam:PassRole it."
  type        = string
}

variable "app_secret_arns" {
  description = "App secret ARNs the deploy role may GetSecretValue on (scoped list, never *)."
  type        = list(string)
  default     = []
}

variable "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN the deploy role may CreateInvalidation on."
  type        = string
}

variable "static_bucket_arn" {
  description = "Static-site S3 bucket ARN the deploy role may sync assets to."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
