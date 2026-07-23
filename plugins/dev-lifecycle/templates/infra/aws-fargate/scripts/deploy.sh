#!/usr/bin/env bash
# Deploy the app to an environment provisioned by the aws-fargate infra block.
# This is the target of the monorepo `just deploy <env>` recipe.
#
# Assumes AWS credentials are ALREADY in the environment via GitHub OIDC
# (aws-actions/configure-aws-credentials with role-to-assume:
# <deploy_role_arn>) — this script NEVER reads or stores long-lived keys. Run
# it from CI (or locally after assuming the deploy role).
#
# Steps (see docs/fragment.md "Deployment"):
#   1. terraform apply with the new image tag (task def -> new image)
#   2. build + push the app image to ECR (scan-on-push, immutable tag)
#   3. sync the static site to S3 + invalidate CloudFront
#   4. run migrations against the new image (one-off task)  [project hook]
#   5. force a new ECS deployment
#
# Idempotent and fail-fast. Requires: terraform, aws, docker.
set -euo pipefail

ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DIR="${ROOT_DIR}/envs/${ENV_NAME}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

if [ ! -d "${ENV_DIR}" ]; then
  echo "deploy: no environment at ${ENV_DIR}" >&2
  exit 1
fi

echo "==> Deploying environment '${ENV_NAME}' (image tag: ${IMAGE_TAG})"
cd "${ENV_DIR}"

# Read the stack's contract outputs (the stack must already be applied once).
terraform init -input=false >/dev/null
ECR_URL="$(terraform output -raw ecr_repository_url)"
CLUSTER="$(terraform output -raw ecs_cluster_name)"
SERVICE="$(terraform output -raw ecs_service_name)"
DISTRIBUTION_ID="$(terraform output -raw cloudfront_distribution_id)"
STATIC_BUCKET="$(terraform output -raw static_bucket_name)"
REGION="${AWS_REGION:-$(aws configure get region || echo us-east-1)}"

# 1. Build + push the app image (immutable tag = the git SHA).
echo "==> Building + pushing ${ECR_URL}:${IMAGE_TAG}"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URL%%/*}"
docker build --target prod -t "${ECR_URL}:${IMAGE_TAG}" "${ROOT_DIR}/../../apps/api"
docker push "${ECR_URL}:${IMAGE_TAG}"

# 2. terraform apply so the task definition points at the new image.
echo "==> terraform apply (app_image_tag=${IMAGE_TAG})"
terraform apply -input=false -auto-approve \
  -var-file=terraform.tfvars \
  -var="app_image_tag=${IMAGE_TAG}"

# 3. Static site: sync built assets + invalidate the CDN. (No-op if there is
#    no built frontend yet.)
if [ -d "${ROOT_DIR}/../../apps/web/dist" ] && [ -n "${STATIC_BUCKET}" ]; then
  echo "==> Syncing static site to ${STATIC_BUCKET} + invalidating CloudFront"
  aws s3 sync "${ROOT_DIR}/../../apps/web/dist" "s3://${STATIC_BUCKET}" --delete
  aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths "/*"
fi

# 4. Migrations on deploy: run as a one-off task against the NEW image before
#    the rollout finishes (the prod image CMD does not migrate). A project
#    wires the exact `alembic upgrade head` / `manage.py migrate` run-task here.
echo "==> (migrations) run 'alembic upgrade head' / 'manage.py migrate' as a one-off task against ${ECR_URL}:${IMAGE_TAG}"

# 5. Roll the service.
echo "==> Forcing new deployment of ${SERVICE} on ${CLUSTER}"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${SERVICE}" \
  --force-new-deployment >/dev/null

echo "==> Deploy of '${ENV_NAME}' triggered."
