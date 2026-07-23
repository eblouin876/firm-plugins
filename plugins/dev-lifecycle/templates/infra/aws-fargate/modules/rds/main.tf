# RDS module: an encrypted, private Postgres instance and the composed
# DATABASE_URL secret (Option A — this module owns the generated master
# password, host, and port, so it composes the URL and stores it in Secrets
# Manager under the secrets module's KMS key).
#
# Security posture (checkov-clean by design): storage_encrypted with a
# dedicated CMK (rotation on), publicly_accessible=false, in private subnets,
# backups + deletion protection on, IAM DB auth on, Performance Insights +
# enhanced monitoring encrypted, Postgres logs exported to CloudWatch. The
# security group has NO ingress in this module — the root adds a single
# ingress rule allowing 5432 from the ECS task SG only.

resource "aws_kms_key" "rds" {
  description             = "${var.name_prefix} RDS storage + performance-insights encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  # Explicit key policy (CKV2_AWS_64): account root admin + IAM delegation.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EnableIAMUserPermissions"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })

  tags = var.tags
}

# Parameter group: query logging (CKV2_AWS_30) + force SSL/TLS in transit
# (CKV2_AWS_69). Query logging is DDL + slow queries (>= 500ms), NOT every
# statement — full statement logging would capture query parameters
# (potential PII) and flood the logs. rds.force_ssl=1 rejects any non-TLS
# connection; the composed DATABASE_URL below carries the driver-correct SSL
# param so the app connects over TLS out of the box.
resource "aws_db_parameter_group" "this" {
  name_prefix = "${var.name_prefix}-pg"
  family      = "postgres${split(".", var.engine_version)[0]}"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = var.tags
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.name_prefix}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

resource "random_password" "master" {
  length = 32
  # No special characters: the value is embedded in a URL (DATABASE_URL)
  # unescaped; 32 alphanumeric chars is ample entropy without URL-encoding
  # hazards.
  special = false
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-subnet-group" })
}

# RDS security group: no ingress here (the root adds 5432-from-ECS-SG-only).
resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds"
  description = "RDS Postgres — ingress only from the ECS task SG (added at root); no egress."
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds" })
}

# --- Enhanced monitoring role ----------------------------------------------

resource "aws_iam_role" "monitoring" {
  name = "${var.name_prefix}-rds-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# --- Instance ---------------------------------------------------------------

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class
  port           = var.db_port

  db_name  = var.db_name
  username = var.db_username
  password = random_password.master.result

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn

  db_subnet_group_name   = aws_db_subnet_group.this.name
  parameter_group_name   = aws_db_parameter_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period   = var.backup_retention_days
  copy_tags_to_snapshot     = true
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-postgres-final"

  iam_database_authentication_enabled = true
  auto_minor_version_upgrade          = true

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.rds.arn
  performance_insights_retention_period = 7

  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.monitoring.arn

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # checkov:skip=CKV_AWS_157:Multi-AZ is opt-in for a starter (cost) — set var.multi_az=true for prod HA.
  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })
}

# --- Composed DATABASE_URL secret (Option A) --------------------------------

resource "aws_secretsmanager_secret" "database_url" {
  name        = "${var.name_prefix}/DATABASE_URL"
  description = "Composed DATABASE_URL (scheme selects FastAPI asyncpg vs Django) — injected into the task via valueFrom."
  kms_key_id  = var.secrets_kms_key_arn

  recovery_window_in_days = 7

  # checkov:skip=CKV2_AWS_57:DB credential rotation is handled at the RDS layer (rotate the master password + re-store), not via a Secrets Manager rotation Lambda on this composed-URL secret (references/security/secrets-management.md, "Rotation").
  tags = var.tags
}

locals {
  # rds.force_ssl requires every client to connect over TLS. Carry the
  # driver-correct SSL param in the URL so the app connects out of the box:
  # SQLAlchemy's asyncpg dialect takes `ssl=require`; libpq (Django/psycopg)
  # takes `sslmode=require`.
  ssl_query = strcontains(var.db_url_scheme, "asyncpg") ? "?ssl=require" : "?sslmode=require"
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = format(
    "%s://%s:%s@%s:%d/%s%s",
    var.db_url_scheme,
    var.db_username,
    random_password.master.result,
    aws_db_instance.this.address,
    var.db_port,
    var.db_name,
    local.ssl_query,
  )
}
