variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "aws_region" {
  description = "AWS region (for the awslogs driver + the logs KMS key policy). A variable, not a data source, so plan stays offline."
  type        = string
}

variable "account_id" {
  description = "AWS account ID (scopes the logs KMS key policy). A variable, not aws_caller_identity."
  type        = string
}

variable "vpc_id" {
  description = "VPC the ALB, task ENIs, and security groups live in."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR — scopes the task security group's Postgres (5432) egress to inside the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_ids" {
  description = "Public subnets for the internet-facing ALB."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnets the Fargate task ENIs attach to (no public IP)."
  type        = list(string)
}

variable "app_image" {
  description = "Full container image reference the task runs (<ecr-url>:<tag>)."
  type        = string
}

variable "container_port" {
  description = "Port the app container listens on."
  type        = number
  default     = 8000
}

variable "desired_count" {
  description = "Number of Fargate tasks."
  type        = number
  default     = 2
}

variable "task_cpu" {
  description = "Task CPU units."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Task memory (MiB)."
  type        = number
  default     = 1024
}

variable "health_check_path" {
  description = "ALB target-group health check path (backend readiness probe)."
  type        = string
  default     = "/readyz"
}

variable "alb_acm_certificate_arn" {
  description = "ACM certificate ARN (this region) for the ALB HTTPS listener."
  type        = string
}

variable "app_environment" {
  description = "Non-secret env vars for the container (plain `environment` — NEVER secrets)."
  type        = map(string)
  default     = {}
}

variable "app_secret_arns" {
  description = "Map of env var name -> Secrets Manager ARN, injected via the task's `secrets`/`valueFrom` (never `environment`, never the image)."
  type        = map(string)
  default     = {}
}

variable "secrets_kms_key_arn" {
  description = "KMS key ARN the app secrets are encrypted with — the execution role is granted kms:Decrypt on exactly this key."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch retention for the task log group (days). Default 365 (>= 1 year)."
  type        = number
  default     = 365
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
