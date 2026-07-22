<!-- fragment: block:components/security/secrets-loading -->

## Setup
Copy `secrets.py` into `app/core/security/secrets.py`. At app startup, call
`validate_required([...])` with every secret name the app needs so a missing
one fails fast before the app serves a single request, not deep inside a
request. Import `get_secret(name)` anywhere a secret is needed instead of
reading `os.environ` directly.

## Secrets
| `SECRETS_BACKEND` | secrets-loading | Optional. Unset (default) resolves env-only; set to `aws-secrets-manager` to enable the AWS Secrets Manager fallback layer. |
| `AWS_SECRETS_MANAGER_PREFIX` | secrets-loading | Optional. Prefix prepended to a secret's name to form its AWS Secrets Manager SecretId (e.g. `prod/myapp/`). |
| `AWS_REGION` | secrets-loading | Required when `SECRETS_BACKEND=aws-secrets-manager` and `AWS_DEFAULT_REGION` isn't already set. Your AWS account's target region. |
