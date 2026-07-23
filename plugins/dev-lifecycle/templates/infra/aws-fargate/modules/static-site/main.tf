# Static-site module: a PRIVATE S3 bucket (all public access blocked, SSE on,
# versioning on, lifecycle configured) fronted by CloudFront with an Origin
# Access Control (OAC) so the bucket is reachable ONLY through the
# distribution — never directly. Viewer protocol is redirect-to-HTTPS; a
# custom-domain deployment pins minimum TLS 1.2 (2021 policy).

resource "aws_s3_bucket" "site" {
  # checkov:skip=CKV_AWS_18:Server access logging writes to a dedicated log bucket — opt-in for a starter (enable aws_s3_bucket_logging to a log bucket).
  # checkov:skip=CKV_AWS_144:Cross-region replication is opt-in for a starter (public web assets are rebuilt/redeployable, not the system of record).
  # checkov:skip=CKV_AWS_145:Public web assets served through CloudFront; SSE-S3 (AES256) satisfies encryption-at-rest. Switch to SSE-KMS (and grant CloudFront OAC + the deploy role kms access) if the bucket ever holds sensitive objects.
  # checkov:skip=CKV2_AWS_62:Event notifications are opt-in — this static-asset bucket has no event consumer (no Lambda/SQS/SNS pipeline).
  bucket = "${var.name_prefix}-static-site"

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    id     = "expire-noncurrent-and-abort-mpu"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# --- CloudFront -------------------------------------------------------------

# Security response headers on every CloudFront response (HSTS, nosniff,
# frame-deny, referrer-policy) — the edge counterpart to the backend's
# SecurityHeadersMiddleware (references/security/secure-baseline.md,
# "Security headers & CSP"). Attached to the default cache behavior below.
resource "aws_cloudfront_response_headers_policy" "site" {
  name = "${var.name_prefix}-security-headers"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name_prefix}-static-oac"
  description                       = "OAC for ${var.name_prefix} static site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  origin_id    = "s3-${aws_s3_bucket.site.id}"
  use_acm_cert = var.cloudfront_acm_certificate_arn != ""
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  default_root_object = var.default_root_object
  comment             = "${var.name_prefix} static site"
  aliases             = var.aliases
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS managed "CachingOptimized" policy id — no cookies/query-string
    # forwarding for static assets.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    # Security response headers (HSTS/nosniff/frame-deny/referrer) on every
    # response (CKV2_AWS_32).
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Viewer certificate: default *.cloudfront.net cert for a domain-less
  # starter, or a custom ACM cert (us-east-1) pinned to TLSv1.2_2021.
  # checkov:skip=CKV_AWS_174:Default *.cloudfront.net certificate negotiates modern TLS server-side; set cloudfront_acm_certificate_arn to serve a custom domain with an explicit TLSv1.2_2021 minimum (the custom-cert branch below sets it).
  dynamic "viewer_certificate" {
    for_each = local.use_acm_cert ? [1] : []
    content {
      acm_certificate_arn      = var.cloudfront_acm_certificate_arn
      ssl_support_method       = "sni-only"
      minimum_protocol_version = "TLSv1.2_2021"
    }
  }

  dynamic "viewer_certificate" {
    for_each = local.use_acm_cert ? [] : [1]
    content {
      cloudfront_default_certificate = true
    }
  }

  # checkov:skip=CKV_AWS_68:WAF is opt-in for a starter static site — attach a WebACL (web_acl_id) when the app warrants it.
  # checkov:skip=CKV2_AWS_47:Log4j WAFv2 rule is part of the opt-in WAF above.
  # checkov:skip=CKV_AWS_86:Access logging writes to a dedicated log bucket — opt-in for a starter (enable logging_config with a log bucket).
  # checkov:skip=CKV_AWS_310:Origin failover (a second origin) is opt-in — this single-origin static bucket has no failover peer.
  # checkov:skip=CKV_AWS_374:Global public static site — geo restriction is "none" by design; set a whitelist/blacklist only if the content is region-limited.
  # checkov:skip=CKV2_AWS_42:Default *.cloudfront.net certificate for a domain-less starter; set cloudfront_acm_certificate_arn to serve a custom domain over a custom ACM cert (the custom-cert branch pins TLSv1.2_2021).
  tags = var.tags
}

# Bucket policy: allow ONLY this CloudFront distribution (via OAC) to read
# objects — the bucket is otherwise fully private.
data "aws_iam_policy_document" "site" {
  statement {
    sid       = "AllowCloudFrontOACRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site.json
}
