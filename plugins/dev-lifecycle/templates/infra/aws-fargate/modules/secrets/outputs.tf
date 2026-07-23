output "kms_key_arn" {
  description = "KMS key ARN encrypting the app secrets (and, via the rds module, DATABASE_URL)."
  value       = aws_kms_key.secrets.arn
}

output "app_secret_arns" {
  description = "Map of app env var name -> Secrets Manager ARN, injected into the task via valueFrom. DATABASE_URL is added by the root from the rds module."
  value = merge(
    { JWT_SIGNING_KEY = aws_secretsmanager_secret.jwt_signing_key.arn },
    var.manage_smtp_secrets ? {
      SMTP_USERNAME = aws_secretsmanager_secret.smtp_username[0].arn
      SMTP_PASSWORD = aws_secretsmanager_secret.smtp_password[0].arn
    } : {},
  )
}
