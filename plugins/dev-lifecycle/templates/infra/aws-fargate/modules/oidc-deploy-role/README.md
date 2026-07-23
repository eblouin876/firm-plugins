<!--
module: oidc-deploy-role
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# oidc-deploy-role module

A GitHub Actions OpenID Connect provider (so CI assumes a role via a
short-lived web-identity token — **no long-lived AWS access keys**) and a
LEAST-PRIVILEGE deploy role whose trust policy is scoped to `github_repo` AND
`github_branch` (`sub = repo:<owner>/<name>:ref:refs/heads/<branch>`).

The role can do ONLY what a deploy does, each action scoped to a specific ARN:
push to this ECR repo, roll this ECS service (`ecs:UpdateService`, cluster
condition), `iam:PassRole` only the two task roles to `ecs-tasks`, read the
provisioned app secrets, invalidate this CloudFront distribution, and sync the
static-site bucket. **There is no `*:*` / admin grant.** The only `*`-resource
statements are `ecr:GetAuthorizationToken` and `ecs:Describe*/
RegisterTaskDefinition`, which AWS does not allow resource-scoping — a single
specific action each, never a wildcard action (`CKV_AWS_356` skipped inline
with that justification).

Set `create_oidc_provider = false` if the account already has the
`token.actions.githubusercontent.com` provider (only one is allowed per
account); the trust policy then references it by a constructed ARN — no data
source, so plan stays offline.

## Inputs (highlights)
| Name | Description |
| --- | --- |
| `name_prefix`, `account_id`, `aws_region` | Naming + offline-safe scoping. |
| `github_repo`, `github_branch` | OIDC trust scope. |
| `create_oidc_provider` | Create the provider (default true). |
| `ecr_repository_arn`, `ecs_cluster_arn`, `ecs_service_arn` | Deploy targets. |
| `task_role_arn`, `execution_role_arn` | PassRole targets. |
| `app_secret_arns` | GetSecretValue scope (list). |
| `cloudfront_distribution_arn`, `static_bucket_arn` | Invalidation + sync targets. |

## Outputs
| Name | Description |
| --- | --- |
| `deploy_role_arn` | Role CI assumes via OIDC (`AWS_OIDC_ROLE_ARN`). |
| `oidc_provider_arn` | The GitHub OIDC provider ARN. |
