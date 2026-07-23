<!--
recipe: file-upload-s3
applies-to:
  - backend block: fastapi OR django (either can mint a presigned URL with boto3)
  - infra block: templates/infra/aws-fargate (the task role a presigned-URL minter runs under)
last-verified: 2026-07-23
provenance: manual
sources:
  - https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html
  - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/generate_presigned_url.html
  - references/security/secure-baseline.md
  - references/security/secrets-management.md
  - templates/infra/aws-fargate/modules/ecs-fargate-service/main.tf
  - templates/infra/aws-fargate/modules/static-site/main.tf
-->

# File upload via S3 (presigned URL)

Wire direct-to-S3 file uploads: the client `PUT`s the file bytes straight to S3 over a short-lived presigned URL; the server never receives, buffers, or re-uploads the file body — it only mints the URL. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Security posture
- Doc fragment

## What this wires
Applying this recipe gives a feature working file uploads without the backend ever touching a file's bytes: an authenticated endpoint mints a presigned `PUT` URL scoped to one object key with a short TTL, the client uploads directly to S3, and the backend's only other job is recording the resulting object key against whatever domain record it belongs to (a user's avatar, an attachment on an order).

It **composes existing pieces** — this recipe's own honest gap is that the kit does not yet ship a dedicated `s3-uploads` Terraform module, so it wires the closest existing infra surfaces rather than a purpose-built one:
- **`templates/infra/aws-fargate/modules/ecs-fargate-service/main.tf`**'s `aws_iam_role.task` — the Fargate task's own runtime IAM identity, which "starts empty" by that module's own comment ("a project grants the app scoped permissions here (e.g. `s3:PutObject` on an uploads bucket) as features require them"). This recipe's IAM grant attaches here, via the module's `task_role_arn` output (already exposed at the root, consumed today by `oidc-deploy-role`).
- **`templates/infra/aws-fargate/modules/static-site/main.tf`** — not reused directly (it's a CloudFront-fronted *public*-read bucket for web assets, the wrong shape for user uploads), but its private-bucket resource set (`aws_s3_bucket` + `aws_s3_bucket_public_access_block` with all four flags `true` + `aws_s3_bucket_ownership_controls` (`BucketOwnerEnforced`) + `aws_s3_bucket_versioning` + `aws_s3_bucket_server_side_encryption_configuration`) is the pattern this recipe's new uploads bucket mirrors, swapping "public via CloudFront OAC" for "private, no bucket policy granting any public/anonymous access at all."
- **`templates/components/security/secrets-loading/secret_store.py`** — not actually needed for AWS credentials (see step 2 — the task role supplies those), but is where any non-secret bucket configuration a project chooses to make overridable (e.g. `UPLOADS_BUCKET_NAME`) resolves from, consistent with how every other piece of runtime config in this kit is read.

## Prerequisites
- `templates/infra/aws-fargate` provisioned (or being extended) — this recipe adds one new S3 bucket resource plus one new IAM policy statement on the existing `ecs-fargate-service` module's task role; it does not stand up a parallel infra stack.
- A backend block (FastAPI or Django) able to run `boto3` — lazily imported, matching `secret_store.py`'s own "only import boto3 once actually needed" convention; no version is pinned for `boto3` on `references/compatibility-matrix.md` yet, so pin it in the block's own `pyproject.toml`/`requirements` against the current PyPI release at implementation time rather than assuming a line.
- An authenticated user context (this recipe assumes the `end-to-end-auth` recipe or equivalent is already wired — a presigned-URL-minting endpoint must be behind auth; an anonymous uploader is out of scope for the wire-up steps below).

## Wire-up steps
1. **Add a private uploads bucket to the infra stack**, mirroring `modules/static-site/main.tf`'s private-bucket resource set: `aws_s3_bucket` (a project-scoped name, e.g. `"${var.name_prefix}-uploads"`), `aws_s3_bucket_public_access_block` with all four flags `true`, `aws_s3_bucket_ownership_controls` (`BucketOwnerEnforced`), `aws_s3_bucket_versioning` (Enabled), and `aws_s3_bucket_server_side_encryption_configuration` (SSE-S3 `AES256`, or SSE-KMS if uploads may hold sensitive content — see that module's own SSE-S3-vs-KMS note). Unlike `static-site`, attach **no** `aws_s3_bucket_policy` — there is no CloudFront OAC principal or any other principal that should read this bucket; every access is a presigned URL issued by the app.

2. **Grant the app's existing task role scoped S3 permissions — nothing else.** On `modules/ecs-fargate-service`'s `aws_iam_role.task` (already exposed as `task_role_arn`), attach an inline policy scoped to `s3:PutObject` / `s3:GetObject` (add `s3:DeleteObject` only if the feature needs user-initiated deletes) on exactly `arn:aws:s3:::<uploads-bucket>/*` — never the bucket ARN itself, never a wildcard across buckets. This is the same "starts empty, a project grants what a feature needs" mechanism the module's own comment already documents for this exact case.
   - **No AWS access key/secret is a project secret here.** `boto3` resolves credentials via its default chain: inside AWS, that's the Fargate task role granted in this step (automatic, no config); in local dev, a developer's own named AWS profile/SSO session. Nothing about this recipe adds a row to `secret_store.py`/Secrets Manager for AWS credentials — introducing a static access key pair here would be a **downgrade** from the task role's temporary, auto-rotated credentials.

3. **Mint the presigned URL server-side, scoped tight.** In the backend, behind the authenticated endpoint: build the object key **server-side**, namespaced per user so one user can never overwrite or address another's object — e.g. `f"uploads/{user_id}/{uuid4()}-{safe_filename}"` (sanitize/derive `safe_filename`, never pass the client's raw filename straight into the key). Call `boto3.client("s3").generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": key, "ContentType": content_type}, ExpiresIn=<short TTL>)` — or `generate_presigned_post` if the client needs to set additional form-field constraints (e.g. an exact `Content-Length` upper bound) at request time.
   - **TTL**: minutes, not hours — long enough for the client to complete one upload attempt (60–300s is typical), short enough that a leaked URL is only a narrow window of exposure.
   - **Content-type**: pass an explicit, allowlisted `ContentType` the client must match exactly (S3 rejects a `PUT` whose `Content-Type` header doesn't match a presigned URL's signed `ContentType` param) — never accept an arbitrary client-declared type unchecked.
   - **Size limit**: `generate_presigned_url` alone does not enforce a max size; use `generate_presigned_post` with a `conditions` list bounding `content-length-range` when a hard server-enforced cap matters, or enforce it after the fact via an S3 event notification / a follow-up `HeadObject` check before marking the upload "accepted" in the domain record.

4. **Record the object key, not the file.** After the client confirms the upload (or after an S3 event notification, for a stronger guarantee than trusting the client's "done" call), persist the object key against the owning domain record. The backend never stores, streams, or re-uploads the file bytes at any point in this flow.

5. **Verify** the security-relevant properties, not just the happy path: a presigned URL rejects an upload after its TTL expires; a `PUT` with a `Content-Type` other than the one signed is rejected by S3; a user's minted key is namespaced under their own `user_id` prefix and the IAM policy's `Resource` pattern would not, even in principle, let the task role touch another prefix differently (it's `/*` for the whole bucket by design, so the actual isolation is the key-namespacing convention in step 3, not IAM — call this out to whoever reviews the wire-up); the bucket has zero public/anonymous read or write path.

## Security posture
- **No public bucket, ever.** All four `aws_s3_bucket_public_access_block` flags `true`; no bucket policy grants any principal other than the app's own task role (via IAM, not a bucket policy) access.
- **Short TTL.** Minutes, not hours or days — bound the exposure window of a leaked presigned URL.
- **Content-type and size constraints signed into the URL**, not merely validated client-side — a client-side check is a UX nicety, not a security control; the presigned URL's own signed params are what S3 actually enforces.
- **Per-user key namespacing**, chosen server-side from the authenticated identity, never from client input — the client never gets to choose which "folder" its object lands in.
- **Least-privilege IAM** on the task role — `s3:PutObject`/`s3:GetObject` (and only `s3:DeleteObject` if actually needed) scoped to `<bucket-arn>/*`, never a wildcard resource, never a broader action set "for convenience."
- **No AWS static credentials anywhere** — the task role (prod) / a developer's own profile (local dev) is the entire credential story; this recipe adds no new secret to `secret_store.py`.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### File upload (S3 presigned URL)
- **Setup:** An authenticated endpoint mints a short-TTL presigned `PUT` URL (`boto3` `generate_presigned_url`/`generate_presigned_post`) scoped to a server-chosen, per-user-namespaced object key on the private `<project>-uploads` S3 bucket; the client uploads directly to S3. The backend never receives the file body — only the object key, recorded against the owning domain record once the upload completes.
- **Secrets:** none. AWS credentials resolve via boto3's default chain — the Fargate task role in AWS (granted scoped `s3:PutObject`/`s3:GetObject` on the uploads bucket), a developer's own AWS profile/SSO locally. No static access key is ever configured as a project secret.
- **Maintenance:** The uploads bucket has all public access blocked and no bucket policy — access is exclusively via presigned URLs the app mints. Widening the task role's S3 permissions (a new bucket, `s3:DeleteObject`) is a Terraform change to `modules/ecs-fargate-service`'s task-role policy, reviewed the same as any other IAM grant.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34). Wires the
existing ecs-fargate-service task role (already documented as the extension
point for exactly this case) and mirrors static-site's private-bucket
resource pattern; the kit has no dedicated s3-uploads Terraform module yet,
noted explicitly above rather than presented as one.
-->
