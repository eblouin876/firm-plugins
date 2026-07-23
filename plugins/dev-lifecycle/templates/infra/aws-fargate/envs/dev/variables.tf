# Inputs for the dev environment root. Placeholder values live in
# terraform.tfvars.example — copy to terraform.tfvars (gitignored) and fill
# per environment. Every value here is a plain variable: this root uses NO
# plan-time API-call data sources (no `aws_caller_identity`,
# `aws_region` data source, etc.), so `terraform plan` runs fully offline
# with no AWS credentials and no cloud calls. `account_id` in particular is
# a VARIABLE for exactly this reason.

variable "aws_region" {
  description = "AWS region this environment is provisioned into."
  type        = string
}

variable "account_id" {
  description = "AWS account ID (12 digits). A variable, not an aws_caller_identity lookup, so plan stays offline. Used to scope IAM/KMS/Secrets ARNs."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "project_name" {
  description = "Short project identifier; used as the name prefix for every resource so a shared account stays legible."
  type        = string
  default     = "app"
}

variable "environment" {
  description = "Environment name (dev/staging/prod). This root is the dev env; copy the directory for others (directory-per-environment)."
  type        = string
  default     = "dev"
}

# --- Networking -------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of Availability Zones to spread public/private subnets across (2 = one NAT per AZ; a starter can drop to 1 to save NAT cost)."
  type        = number
  default     = 2
}

# --- Application image -------------------------------------------------------

variable "app_image_tag" {
  description = "Container image tag the ECS task definition runs (e.g. a git SHA). The deploy pipeline pushes this tag to ECR, then forces a new deployment."
  type        = string
  default     = "latest"
}

variable "container_port" {
  description = "Port the app container listens on (matches the backend block's EXPOSE, 8000)."
  type        = number
  default     = 8000
}

variable "app_environment" {
  description = "Non-secret environment variables injected into the task (plain `environment`, never secrets — secrets go through Secrets Manager valueFrom). e.g. { ENVIRONMENT = \"production\" }."
  type        = map(string)
  default     = {}
}

variable "desired_count" {
  description = "Number of Fargate tasks to run behind the ALB."
  type        = number
  default     = 2
}

variable "task_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 1024
}

variable "health_check_path" {
  description = "HTTP path the ALB target group health check hits (the backend block's readiness probe)."
  type        = string
  default     = "/readyz"
}

# --- Database ----------------------------------------------------------------

variable "db_url_scheme" {
  description = "URL scheme for the composed DATABASE_URL so both backend tracks work: 'postgresql+asyncpg' (FastAPI/SQLAlchemy async) or 'postgresql' (Django)."
  type        = string
  default     = "postgresql+asyncpg"

  validation {
    condition     = contains(["postgresql+asyncpg", "postgresql"], var.db_url_scheme)
    error_message = "db_url_scheme must be 'postgresql+asyncpg' (FastAPI) or 'postgresql' (Django)."
  }
}

variable "db_name" {
  description = "Initial database name created on the RDS instance."
  type        = string
  default     = "app"
}

variable "db_username" {
  description = "Master username for the RDS Postgres instance. The password is generated (random_password) and never set here — see the rds module."
  type        = string
  default     = "app"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GiB)."
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "Postgres major/minor engine version (matrix Data row pins PostgreSQL 18.x)."
  type        = string
  default     = "18.4"
}

# --- TLS certificates --------------------------------------------------------

variable "alb_acm_certificate_arn" {
  description = "ACM certificate ARN (in this region) for the ALB HTTPS listener. Required — the ALB is HTTPS-only with an HTTP->HTTPS redirect."
  type        = string
}

variable "cloudfront_acm_certificate_arn" {
  description = "ACM certificate ARN (MUST be in us-east-1) for the CloudFront distribution's custom domain. Empty = use the default *.cloudfront.net certificate (no custom domain)."
  type        = string
  default     = ""
}

variable "cloudfront_aliases" {
  description = "Custom domain names (CNAMEs) served by the CloudFront distribution. Requires cloudfront_acm_certificate_arn covering them. Empty for the default cloudfront.net domain."
  type        = list(string)
  default     = []
}

# --- CI / OIDC ---------------------------------------------------------------

variable "github_repo" {
  description = "GitHub repository the deploy role trusts, as 'owner/name'. The OIDC trust policy is scoped to this repo (and branch below) — no other repo can assume the role."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repo))
    error_message = "github_repo must be 'owner/name'."
  }
}

variable "github_branch" {
  description = "Git branch the deploy role trusts (e.g. 'main'). The OIDC `sub` claim is scoped to refs/heads/<branch> so only this branch's workflows can assume the role."
  type        = string
  default     = "main"
}

variable "create_oidc_provider" {
  description = "Whether to create the GitHub Actions OIDC provider in this account. Set false if the account already has one (only one token.actions.githubusercontent.com provider is allowed per account)."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags merged onto every resource (project/env are added automatically)."
  type        = map(string)
  default     = {}
}
