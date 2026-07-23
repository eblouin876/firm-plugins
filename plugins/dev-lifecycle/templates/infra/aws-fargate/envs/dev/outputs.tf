# Contract outputs — what this stack exposes to a deploy pipeline and to the
# rest of the monorepo (the block's `exposes`).

output "ecr_repository_url" {
  description = "ECR repository URL the CI pipeline pushes the app image to."
  value       = module.ecr.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name (for `aws ecs update-service --cluster`)."
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name (for a force-new-deployment on deploy)."
  value       = module.ecs.service_name
}

output "alb_dns_name" {
  description = "Public DNS name of the ALB (point Route 53 / your domain at this)."
  value       = module.ecs.alb_dns_name
}

output "cloudfront_domain_name" {
  description = "CloudFront domain serving the static site."
  value       = module.static_site.cloudfront_domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for `aws cloudfront create-invalidation`)."
  value       = module.static_site.cloudfront_distribution_id
}

output "static_bucket_name" {
  description = "Static-site S3 bucket name (for `aws s3 sync` in the deploy script)."
  value       = module.static_site.bucket_name
}

output "app_secret_arns" {
  description = "Map of app env var name -> Secrets Manager ARN (DATABASE_URL, JWT_SIGNING_KEY, SMTP_*). Injected into the task via valueFrom; also the deploy role's GetSecretValue scope."
  value       = local.app_secret_arns
}

output "deploy_role_arn" {
  description = "Least-privilege deploy role ARN CI assumes via GitHub OIDC (AWS_OIDC_ROLE_ARN)."
  value       = module.oidc_deploy_role.deploy_role_arn
}
