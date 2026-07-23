output "database_url_secret_arn" {
  description = "Secrets Manager ARN of the composed DATABASE_URL — mapped to the DATABASE_URL env var via the task's valueFrom."
  value       = aws_secretsmanager_secret.database_url.arn
}

output "security_group_id" {
  description = "RDS security group ID — the root attaches the ECS-only 5432 ingress rule to it."
  value       = aws_security_group.rds.id
}

output "endpoint" {
  description = "RDS connection endpoint (host)."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "RDS port."
  value       = var.db_port
}
