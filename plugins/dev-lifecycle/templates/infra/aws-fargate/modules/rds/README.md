<!--
module: rds
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# rds module

An encrypted, private Postgres instance and the composed `DATABASE_URL` secret
(Option A — this module owns the generated master password, host, and port, so
it composes the URL and stores it in Secrets Manager under the secrets
module's KMS key).

Secure by default: `storage_encrypted` with a dedicated CMK (rotation on),
`publicly_accessible = false`, private subnets, backups + deletion protection,
IAM DB auth, Performance Insights + enhanced monitoring encrypted, Postgres
logs exported to CloudWatch, and a parameter group forcing **TLS in transit**
(`rds.force_ssl = 1`) plus DDL/slow-query logging.

**TLS:** because `rds.force_ssl = 1` rejects non-TLS connections, the composed
`DATABASE_URL` carries the driver-correct SSL param — `?ssl=require` for the
FastAPI/asyncpg scheme, `?sslmode=require` for the Django scheme — so the app
connects over TLS out of the box.

The security group has **no ingress in this module** — the root env adds a
single rule allowing 5432 from the ECS task SG only, so neither module depends
on the other's SG (no cycle).

## Inputs (highlights)
| Name | Description |
| --- | --- |
| `name_prefix`, `account_id`, `vpc_id`, `private_subnet_ids` | Placement + policy scoping. |
| `db_name`, `db_username`, `db_port` | Database identity. |
| `db_url_scheme` | `postgresql+asyncpg` (FastAPI) or `postgresql` (Django). |
| `instance_class`, `allocated_storage`, `max_allocated_storage`, `engine_version` | Sizing. |
| `backup_retention_days`, `multi_az` | Durability/HA (multi_az opt-in). |
| `secrets_kms_key_arn` | KMS key for the DATABASE_URL secret (from secrets module). |
| `tags` | Tags applied to every resource. |

## Outputs
| Name | Description |
| --- | --- |
| `database_url_secret_arn` | Secrets Manager ARN of the composed DATABASE_URL. |
| `security_group_id` | RDS SG (root attaches the ECS-only 5432 ingress). |
| `endpoint`, `port` | Connection host + port. |
