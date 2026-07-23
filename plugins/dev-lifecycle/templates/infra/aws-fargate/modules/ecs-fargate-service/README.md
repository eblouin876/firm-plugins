<!--
module: ecs-fargate-service
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# ecs-fargate-service module

An internet-facing ALB (HTTPS-only, HTTP->HTTPS redirect, drop-invalid-headers,
deletion protection) in the public subnets, a Fargate service whose task ENIs
sit in the PRIVATE subnets with **no public IP**, a hardened task definition,
split task-role vs execution-role, and a KMS-encrypted CloudWatch log group.

**Traffic path:** internet -> ALB SG (80/443 public) -> ECS task SG (only from
the ALB SG, only on the container port) -> app. Task egress is scoped to 443
(AWS APIs/ECR/Secrets/logs via NAT) and 5432 within the VPC (RDS).

**Hardened task:** non-root (`user = "1000:1000"`), `readonlyRootFilesystem =
true` (with a writable `/tmp` volume), secrets injected via
`secrets`/`valueFrom` (never `environment`, never the image), awslogs to the
KMS-encrypted group. The **execution role** is granted `GetSecretValue` on
exactly the app secret ARNs and `kms:Decrypt` on exactly the secrets key —
nothing wildcarded. The **task role** starts empty (the app needs no AWS perms
by default); a project grants it scoped perms as features require.

## Inputs (highlights)
| Name | Description |
| --- | --- |
| `name_prefix`, `aws_region`, `account_id` | Naming + offline-safe scoping. |
| `vpc_id`, `vpc_cidr`, `public_subnet_ids`, `private_subnet_ids` | Placement. |
| `app_image`, `container_port`, `desired_count`, `task_cpu`, `task_memory` | Task sizing. |
| `health_check_path` | ALB target-group health check (readiness probe). |
| `alb_acm_certificate_arn` | ACM cert (this region) for the HTTPS listener. |
| `app_environment` | Non-secret env vars (never secrets). |
| `app_secret_arns` | Map env var -> Secrets Manager ARN (valueFrom). |
| `secrets_kms_key_arn` | KMS key the execution role may decrypt. |
| `log_retention_days` | Log retention (default 365). |

## Outputs
| Name | Description |
| --- | --- |
| `cluster_name`, `cluster_arn`, `service_name`, `service_arn` | ECS identity (deploy scope). |
| `alb_dns_name`, `alb_arn` | Public ALB. |
| `security_group_id` | Task SG (root attaches the RDS ingress referencing it). |
| `task_role_arn`, `execution_role_arn` | The two roles (deploy-role PassRole scope). |
| `log_group_name` | CloudWatch log group. |
