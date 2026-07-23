variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Scopes the KMS key policy — a variable, not aws_caller_identity, so plan stays offline."
  type        = string
}

variable "repository_name" {
  description = "ECR repository name (the app image lives here)."
  type        = string
}

variable "untagged_expiry_days" {
  description = "Expire untagged images after this many days (lifecycle policy)."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
