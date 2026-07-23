variable "name_prefix" {
  description = "Prefix for resource names; also the Secrets Manager path prefix."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Scopes the KMS key policy — a variable, not aws_caller_identity, so plan stays offline."
  type        = string
}

variable "manage_smtp_secrets" {
  description = "Create SMTP_USERNAME/SMTP_PASSWORD secret containers (values filled out-of-band by the operator). Set false for a project without email."
  type        = bool
  default     = true
}

variable "recovery_window_in_days" {
  description = "Secrets Manager recovery window on delete. 7 keeps a real recovery buffer; a throwaway dev stack can set 0 for immediate delete."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
