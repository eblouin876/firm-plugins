# Dev environment root — composes the seven reusable modules under
# ../../modules/ into one deployable stack (directory-per-environment, per
# references/infra/terraform.md). Copy this directory to envs/staging,
# envs/prod for other environments; they diverge via their own tfvars, not
# conditional logic here.
#
# Credential-free verification: the provider below sets
# skip_credentials_validation / skip_requesting_account_id /
# skip_metadata_api_check so `terraform validate` and
# `terraform plan -var-file=terraform.tfvars.example` run with NO real AWS
# credentials and NO cloud calls (dummy AWS_ACCESS_KEY_ID/SECRET are enough
# to construct the provider; nothing here reaches STS or the metadata API).
# There is NO `terraform apply` in verification — plan only.

provider "aws" {
  region = var.aws_region

  # Offline/plan-safe: never call STS GetCallerIdentity, the account-id
  # endpoint, or the EC2 metadata API at plan time. Real credentials
  # (OIDC-assumed role in CI) are still required for `apply`.
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true

  default_tags {
    tags = local.tags
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags,
  )

  # ECR image reference the task definition runs: <repo-url>:<tag>.
  app_image = "${module.ecr.repository_url}:${var.app_image_tag}"

  # ENV_VAR -> Secrets Manager ARN map injected into the task via
  # `secrets`/`valueFrom` (NEVER `environment`, NEVER the image). The app
  # reads each name from process env (secret_store.py, process-env-first).
  app_secret_arns = merge(
    module.secrets.app_secret_arns,
    { DATABASE_URL = module.rds.database_url_secret_arn },
  )
}

module "network" {
  source = "../../modules/network"

  name_prefix = local.name_prefix
  region      = var.aws_region
  account_id  = var.account_id
  vpc_cidr    = var.vpc_cidr
  az_count    = var.az_count
  tags        = local.tags
}

module "ecr" {
  source = "../../modules/ecr"

  name_prefix     = local.name_prefix
  account_id      = var.account_id
  repository_name = var.project_name
  tags            = local.tags
}

module "secrets" {
  source = "../../modules/secrets"

  name_prefix = local.name_prefix
  account_id  = var.account_id
  tags        = local.tags
}

module "rds" {
  source = "../../modules/rds"

  name_prefix         = local.name_prefix
  account_id          = var.account_id
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  db_name             = var.db_name
  db_username         = var.db_username
  db_url_scheme       = var.db_url_scheme
  instance_class      = var.db_instance_class
  allocated_storage   = var.db_allocated_storage
  engine_version      = var.db_engine_version
  secrets_kms_key_arn = module.secrets.kms_key_arn
  tags                = local.tags
}

module "static_site" {
  source = "../../modules/static-site"

  name_prefix                    = local.name_prefix
  cloudfront_acm_certificate_arn = var.cloudfront_acm_certificate_arn
  aliases                        = var.cloudfront_aliases
  tags                           = local.tags
}

module "ecs" {
  source = "../../modules/ecs-fargate-service"

  name_prefix             = local.name_prefix
  aws_region              = var.aws_region
  account_id              = var.account_id
  vpc_id                  = module.network.vpc_id
  vpc_cidr                = var.vpc_cidr
  public_subnet_ids       = module.network.public_subnet_ids
  private_subnet_ids      = module.network.private_subnet_ids
  app_image               = local.app_image
  container_port          = var.container_port
  desired_count           = var.desired_count
  task_cpu                = var.task_cpu
  task_memory             = var.task_memory
  health_check_path       = var.health_check_path
  alb_acm_certificate_arn = var.alb_acm_certificate_arn
  app_environment         = var.app_environment
  app_secret_arns         = local.app_secret_arns
  secrets_kms_key_arn     = module.secrets.kms_key_arn
  tags                    = local.tags
}

module "oidc_deploy_role" {
  source = "../../modules/oidc-deploy-role"

  name_prefix                 = local.name_prefix
  account_id                  = var.account_id
  aws_region                  = var.aws_region
  github_repo                 = var.github_repo
  github_branch               = var.github_branch
  create_oidc_provider        = var.create_oidc_provider
  ecr_repository_arn          = module.ecr.repository_arn
  ecs_cluster_arn             = module.ecs.cluster_arn
  ecs_service_arn             = module.ecs.service_arn
  task_role_arn               = module.ecs.task_role_arn
  execution_role_arn          = module.ecs.execution_role_arn
  app_secret_arns             = values(local.app_secret_arns)
  cloudfront_distribution_arn = module.static_site.cloudfront_distribution_arn
  static_bucket_arn           = module.static_site.bucket_arn
  tags                        = local.tags
}

# ECS -> RDS access: allow the Fargate task security group to reach Postgres
# on 5432, and nothing else. Placed at the root (not inside either module) so
# neither the rds nor the ecs module depends on the other's security group —
# breaking what would otherwise be a module-level dependency cycle (ecs needs
# the DB secret ARN from rds; rds would need the ecs SG id). The rule lives on
# the RDS SG; the ECS task SG is the only allowed source.
resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs" {
  security_group_id            = module.rds.security_group_id
  referenced_security_group_id = module.ecs.security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Postgres from the Fargate task security group only"

  tags = local.tags
}
