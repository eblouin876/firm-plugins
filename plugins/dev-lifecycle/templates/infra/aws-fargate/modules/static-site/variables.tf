variable "name_prefix" {
  description = "Prefix for resource names; also the S3 bucket name base."
  type        = string
}

variable "cloudfront_acm_certificate_arn" {
  description = "ACM cert ARN (MUST be us-east-1) for a custom domain. Empty = default *.cloudfront.net certificate."
  type        = string
  default     = ""
}

variable "aliases" {
  description = "Custom domain CNAMEs for the distribution (requires cloudfront_acm_certificate_arn covering them)."
  type        = list(string)
  default     = []
}

variable "default_root_object" {
  description = "Object CloudFront returns for the root path."
  type        = string
  default     = "index.html"
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
