<!--
module: network
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# network module

VPC with public + private subnets across `az_count` AZs, an internet gateway,
one NAT gateway per AZ, route tables, VPC flow logs to a KMS-encrypted
CloudWatch log group, and a locked-down default security group. Data stores
and tasks live in the private subnets; only the ALB is public.

**Offline-plan note:** AZ names are derived from `region` + `[a,b,c…]` (or the
explicit `availability_zones` list) — no `aws_availability_zones` data source,
so `terraform plan` never calls AWS.

## Inputs
| Name | Description |
| --- | --- |
| `name_prefix` | Resource name prefix. |
| `region` | AWS region (derives AZ names, scopes the flow-log KMS policy). |
| `account_id` | AWS account ID (scopes the flow-log KMS policy). |
| `vpc_cidr` | VPC CIDR (default `10.0.0.0/16`). |
| `az_count` | AZs to span (default 2). |
| `availability_zones` | Explicit AZ list (default: derived from region). |
| `flow_log_retention_days` | Flow-log retention (default 365). |
| `tags` | Tags applied to every resource. |

## Outputs
| Name | Description |
| --- | --- |
| `vpc_id` | VPC ID. |
| `public_subnet_ids` | Public subnet IDs (ALB tier). |
| `private_subnet_ids` | Private subnet IDs (ECS + RDS tier). |
