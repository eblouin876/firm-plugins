variable "name_prefix" {
  description = "Prefix for all resource names (e.g. \"app-dev\")."
  type        = string
}

variable "region" {
  description = "AWS region. Used to derive AZ names (region + letter) WITHOUT an aws_availability_zones data source, so plan stays offline, and to scope the flow-log KMS key policy."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Scopes the flow-log KMS key policy — a variable, not aws_caller_identity, so plan stays offline."
  type        = string
}

variable "availability_zones" {
  description = "Explicit AZ names to place subnets in. Empty (default) derives them as region + [a,b,c...] for az_count — offline, no data source. Override for accounts where those AZ letters aren't available."
  type        = list(string)
  default     = []
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of AZs to spread public + private subnets across."
  type        = number
  default     = 2
}

variable "flow_log_retention_days" {
  description = "CloudWatch retention for VPC flow logs (days). Defaults to 365 (>= 1 year)."
  type        = number
  default     = 365
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
