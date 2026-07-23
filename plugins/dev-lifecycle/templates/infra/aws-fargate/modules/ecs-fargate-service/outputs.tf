output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  description = "ECS cluster ARN — scoped target for the deploy role's ecs:UpdateService."
  value       = aws_ecs_cluster.this.arn
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "service_arn" {
  description = "ECS service ARN."
  value       = aws_ecs_service.this.id
}

output "alb_dns_name" {
  description = "Public DNS name of the ALB."
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  description = "ALB ARN."
  value       = aws_lb.this.arn
}

output "security_group_id" {
  description = "Fargate task security group ID — the root attaches the RDS 5432 ingress rule referencing it."
  value       = aws_security_group.tasks.id
}

output "task_role_arn" {
  description = "Task role ARN (the app's runtime identity)."
  value       = aws_iam_role.task.arn
}

output "execution_role_arn" {
  description = "Execution role ARN (image pull + secret injection)."
  value       = aws_iam_role.execution.arn
}

output "log_group_name" {
  description = "CloudWatch log group the task streams to."
  value       = aws_cloudwatch_log_group.app.name
}
