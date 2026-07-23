variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Scopes the RDS KMS key policy — a variable, not aws_caller_identity, so plan stays offline."
  type        = string
}

variable "vpc_id" {
  description = "VPC the RDS instance and its security group live in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group — the instance is never in a public subnet."
  type        = list(string)
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "app"
}

variable "db_username" {
  description = "Master username. The password is generated (random_password), never set by hand."
  type        = string
  default     = "app"
}

variable "db_port" {
  description = "Postgres port."
  type        = number
  default     = 5432
}

variable "db_url_scheme" {
  description = "Scheme for the composed DATABASE_URL: 'postgresql+asyncpg' (FastAPI) or 'postgresql' (Django)."
  type        = string
  default     = "postgresql+asyncpg"
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Allocated storage (GiB)."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Upper bound for storage autoscaling (GiB). Set >= allocated_storage."
  type        = number
  default     = 100
}

variable "engine_version" {
  description = "Postgres engine version (matrix Data row: PostgreSQL 18.x)."
  type        = string
  default     = "18.4"
}

variable "backup_retention_days" {
  description = "Automated backup retention (days). Must be > 0."
  type        = number
  default     = 7
}

variable "multi_az" {
  description = "Multi-AZ standby. Off by default for a starter (cost); turn on for prod HA."
  type        = bool
  default     = false
}

variable "secrets_kms_key_arn" {
  description = "KMS key ARN (from the secrets module) encrypting the composed DATABASE_URL secret."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
