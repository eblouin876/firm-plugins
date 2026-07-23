output "deploy_role_arn" {
  description = "ARN of the least-privilege deploy role CI assumes via OIDC (set as AWS_OIDC_ROLE_ARN / role-to-assume)."
  value       = aws_iam_role.deploy.arn
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider (created here, or the pre-existing one referenced by ARN)."
  value       = local.oidc_provider_arn
}
