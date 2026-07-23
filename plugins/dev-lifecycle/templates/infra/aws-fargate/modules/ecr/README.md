<!--
module: ecr
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# ecr module

One private ECR repository for the app image: KMS-encrypted (dedicated key,
rotation on), scan-on-push, and IMMUTABLE tags so a pushed tag can never be
overwritten. An untagged-image lifecycle rule keeps storage/scan noise down.

## Inputs
| Name | Description |
| --- | --- |
| `name_prefix` | Resource name prefix. |
| `account_id` | AWS account ID (scopes the KMS key policy). |
| `repository_name` | Repository name. |
| `untagged_expiry_days` | Expire untagged images after N days (default 14). |
| `tags` | Tags applied to every resource. |

## Outputs
| Name | Description |
| --- | --- |
| `repository_url` | Repository URL (`<url>:<tag>` the task pulls). |
| `repository_arn` | Repository ARN (deploy-role push scope). |
| `kms_key_arn` | Encryption key ARN. |
