output "repository_url" {
  description = "ECR repository URL the task definition pulls the image from (<url>:<tag>)."
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "ECR repository ARN — scoped target for the deploy role's push permissions."
  value       = aws_ecr_repository.this.arn
}

output "kms_key_arn" {
  description = "KMS key ARN encrypting the repository."
  value       = aws_kms_key.ecr.arn
}
