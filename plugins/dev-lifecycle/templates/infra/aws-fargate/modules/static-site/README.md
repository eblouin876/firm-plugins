<!--
module: static-site
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# static-site module

A PRIVATE S3 bucket (all public access blocked, SSE on, versioning on,
lifecycle configured) fronted by CloudFront with an Origin Access Control
(OAC) so the bucket is reachable ONLY through the distribution — never
directly. Viewer protocol is redirect-to-HTTPS, a security response-headers
policy (HSTS/nosniff/frame-deny/referrer) is attached, and a custom-domain
deployment pins minimum TLS 1.2 (2021 policy).

For a domain-less starter the default `*.cloudfront.net` certificate is used;
set `cloudfront_acm_certificate_arn` (us-east-1) + `aliases` to serve a custom
domain with an explicit `TLSv1.2_2021` minimum. Opt-in items (WAF, access
logging, geo restriction, cross-region replication, SSE-KMS) are skipped inline
with justifications.

## Inputs
| Name | Description |
| --- | --- |
| `name_prefix` | Resource name prefix / bucket name base. |
| `cloudfront_acm_certificate_arn` | Custom-domain cert (us-east-1); empty = default cert. |
| `aliases` | Custom domain CNAMEs. |
| `default_root_object` | Root object (default `index.html`). |
| `tags` | Tags applied to every resource. |

## Outputs
| Name | Description |
| --- | --- |
| `bucket_name`, `bucket_arn` | The private asset bucket. |
| `cloudfront_domain_name` | Public URL for the assets. |
| `cloudfront_distribution_id` | Invalidation target. |
| `cloudfront_distribution_arn` | Distribution ARN. |
