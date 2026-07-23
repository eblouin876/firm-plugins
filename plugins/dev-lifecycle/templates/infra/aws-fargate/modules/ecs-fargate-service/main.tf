# ECS Fargate service module: an internet-facing ALB (HTTPS-only, HTTP->HTTPS
# redirect) in the public subnets, a Fargate service whose task ENIs sit in
# the PRIVATE subnets with no public IP, a hardened task definition
# (non-root, read-only root filesystem, secrets via valueFrom), split
# task-role vs execution-role, and a KMS-encrypted CloudWatch log group.
#
# Traffic path: internet -> ALB SG (80/443 public) -> ECS task SG (only from
# the ALB SG, only on the container port) -> app. The task's egress is scoped
# to 443 (AWS APIs/ECR/Secrets/logs via NAT) and 5432 within the VPC (RDS).

# --- Security groups --------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "ALB — public HTTPS/HTTP ingress; egress only to the ECS task SG."
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

# Public ingress is the ALB's entire job (the app tier stays private behind
# it). CKV_AWS_260 (0.0.0.0/0 -> 80) is justified; the :80 listener only
# 301-redirects to :443.
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  # checkov:skip=CKV_AWS_260:Public ingress on 80 is the ALB's purpose; the :80 listener only redirects to HTTPS. The app tier is private behind this ALB.
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP from the internet (redirected to HTTPS)"

  tags = var.tags
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS from the internet"

  tags = var.tags
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
  description                  = "To the Fargate tasks on the container port only"

  tags = var.tags
}

resource "aws_security_group" "tasks" {
  name        = "${var.name_prefix}-tasks"
  description = "Fargate tasks — ingress only from the ALB SG; scoped egress."
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name_prefix}-tasks" })
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
  description                  = "App traffic from the ALB only"

  tags = var.tags
}

resource "aws_vpc_security_group_egress_rule" "tasks_https" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS egress to AWS APIs (ECR pull, Secrets Manager, CloudWatch) via NAT"

  tags = var.tags
}

resource "aws_vpc_security_group_egress_rule" "tasks_postgres" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = var.vpc_cidr
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  description       = "Postgres egress to RDS inside the VPC"

  tags = var.tags
}

# --- CloudWatch log group (KMS-encrypted) -----------------------------------

resource "aws_kms_key" "logs" {
  description             = "${var.name_prefix} ECS task log-group encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableIAMUserPermissions"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowCloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.aws_region}.amazonaws.com" }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:*"
          }
        }
      },
    ]
  })

  tags = var.tags
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${var.name_prefix}-ecs-logs"
  target_key_id = aws_kms_key.logs.key_id
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/${var.name_prefix}/ecs/app"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn

  tags = var.tags
}

# --- IAM: execution role (pull image, read secrets, write logs) -------------

resource "aws_iam_role" "execution" {
  name = "${var.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

# AWS-managed execution policy (ECR pull + base CloudWatch Logs).
resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Least-privilege inline policy: GetSecretValue on exactly the app secret
# ARNs, and kms:Decrypt on exactly the secrets KMS key — nothing wildcarded.
data "aws_iam_policy_document" "execution_secrets" {
  count = length(var.app_secret_arns) > 0 ? 1 : 0

  statement {
    sid       = "ReadAppSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = values(var.app_secret_arns)
  }

  statement {
    sid       = "DecryptSecretsKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  count = length(var.app_secret_arns) > 0 ? 1 : 0

  name   = "${var.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets[0].json
}

# --- IAM: task role (the app's own runtime identity) ------------------------
# Starts empty — the running app needs no AWS permissions by default (it reads
# secrets from env, injected by the execution role at start). A project grants
# the app scoped permissions here (e.g. s3:PutObject on an uploads bucket) as
# features require them.
resource "aws_iam_role" "task" {
  name = "${var.name_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

# --- ALB --------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  internal           = false
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]

  drop_invalid_header_fields = true
  enable_deletion_protection = true
  desync_mitigation_mode     = "defensive"

  # checkov:skip=CKV_AWS_91:ALB access logging writes to a dedicated log bucket — opt-in for a starter (set access_logs to an encrypted log bucket).
  # checkov:skip=CKV2_AWS_28:WAF (WebACL association) is opt-in for a starter — attach one when the app warrants it.
  tags = var.tags
}

resource "aws_lb_target_group" "this" {
  name        = "${var.name_prefix}-tg"
  port        = var.container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = var.health_check_path
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  tags = var.tags
}

# HTTPS listener (TLS 1.2 minimum via the 2021-06 policy).
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  tags = var.tags
}

# HTTP listener: 301-redirect to HTTPS (no plaintext forwarding).
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }

  tags = var.tags
}

# --- ECS cluster + task + service -------------------------------------------

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

locals {
  container_name = "${var.name_prefix}-app"

  environment = [for k, v in var.app_environment : { name = k, value = v }]
  # Secrets injected via valueFrom — each maps a Secrets Manager ARN to the
  # exact env var name the app reads process-env-first (secret_store.py).
  secrets = [for name, arn in var.app_secret_arns : { name = name, valueFrom = arn }]
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name_prefix}-app"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # Writable ephemeral scratch for /tmp, so readonlyRootFilesystem can stay
  # true without breaking apps that write temp files.
  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = var.app_image
      essential = true

      # Non-root (uid:gid 1000, matching the backend Dockerfile's `app` user)
      # and a read-only root filesystem — least privilege at runtime.
      user                   = "1000:1000"
      readonlyRootFilesystem = true

      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]

      environment = local.environment
      secrets     = local.secrets

      mountPoints = [{
        sourceVolume  = "tmp"
        containerPath = "/tmp"
        readOnly      = false
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "this" {
  name            = "${var.name_prefix}-app"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = local.container_name
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.http_redirect,
  ]

  tags = var.tags
}
