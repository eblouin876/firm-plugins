output "bucket_name" {
  description = "Name of the private static-site S3 bucket."
  value       = aws_s3_bucket.site.id
}

output "bucket_arn" {
  description = "ARN of the static-site bucket — scoped target for the deploy role's s3:sync."
  value       = aws_s3_bucket.site.arn
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (the public URL for the static assets)."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — the deploy role scopes cache invalidation to it."
  value       = aws_cloudfront_distribution.site.id
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN."
  value       = aws_cloudfront_distribution.site.arn
}
