<!--
library: data-protection
versions-covered: "n/a — practice doc"
last-verified: 2026-07-21
provenance: manual
sources:
  - https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html
  - https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html
  - https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html
-->

# Data protection

PII and sensitive-data handling: what to collect, how it's protected in transit and at rest, how long it's kept, and who can see it. Specializes `references/security/secure-baseline.md` for data specifically.

## Contents
- Version check (do this first)
- Data classification & minimization
- Encryption in transit
- Encryption at rest (RDS/S3)
- Field-level handling of sensitive data
- Retention & deletion
- Access control & logging
- Backups

## Version check (do this first)
Not a library reference — no version axis. The AWS mechanics here (RDS/S3 encryption, automated backups) are stable service features; re-verify current defaults against AWS docs if a service's default posture is ever in question.

## Data classification & minimization
- Before storing any field, classify it: public, internal, sensitive (PII — name, email, address, phone), or restricted (payment data, government IDs, health data, credentials). The classification decides everything downstream — encryption, retention, access.
- **Minimize collection.** Don't add a field "in case it's useful later." Every stored field is something to protect, retain correctly, and eventually delete — collect only what the feature actually needs.
- Restricted-tier data (payment/health/government-ID) usually shouldn't be stored by the app at all — tokenize (see `references/security/payments-security.md`) or delegate to a compliant third party instead of taking on the scope.

## Encryption in transit
- TLS everywhere, per `references/security/secure-baseline.md` — this applies to internal service-to-service traffic too, not just the public edge, whenever it crosses a network boundary (app → RDS, app → S3, service → service across a VPC).
- Database connections use `sslmode=require` (or stricter) for Postgres; don't rely on "it's inside the VPC so it's fine" as the only control.

## Encryption at rest (RDS/S3)
- **RDS:** enable encryption at rest at creation time (`StorageEncrypted`, AWS-managed or a customer-managed KMS key) — it cannot be turned on for an existing unencrypted instance without a migration. Default this on for every environment, including dev/staging.
- **S3:** default bucket encryption (SSE-S3 or SSE-KMS) enabled on every bucket; block public access at the bucket level unless a bucket is explicitly and deliberately public (static asset hosting behind CloudFront, not user data).
- Prefer customer-managed KMS keys over AWS-managed defaults when a project needs key rotation control or an audit trail of key usage; AWS-managed keys are an acceptable default otherwise.

## Field-level handling of sensitive data
- For data more sensitive than the bucket/instance-level encryption above covers (SSNs, health data if the project ever touches it), add field-level encryption or tokenization at the application layer — instance-level encryption protects against a stolen disk, not against a SQL injection reading live rows.
- Mask or truncate sensitive fields in anything non-production: logs, error messages, admin UIs, and especially seed/fixture data (see `references/authoring` seeding conventions where applicable) — never copy real production PII into a lower environment unmasked.
- Never put PII in URLs, query strings, or client-side analytics events — these end up in access logs and third-party tools outside the app's control.

## Retention & deletion
- Every sensitive-tier field has an explicit retention period tied to why it's kept (active-account lifetime, a legal/tax retention window, etc.) — "forever" is a decision, not a default.
- Support actual deletion, not just a `deleted_at` soft-delete flag, for anything a user has a right to have erased — a soft delete that never hard-deletes is not deletion.
- Automate retention where practical (scheduled job purging expired records) rather than relying on someone remembering to run a script.

## Access control & logging
- Access to sensitive/restricted data is scoped by role and enforced server-side, same as `references/security/secure-baseline.md`'s authorization control — an admin panel that can query any user's PII needs its own access check, not just "you're logged in as an admin."
- Log access to restricted-tier data (who viewed/exported which record, when) as part of the audit trail — this is often a compliance requirement, not just good practice, for health or financial data.
- Bulk export/download paths for sensitive data are a common gap — audit them the same as individual-record access, and rate-limit them.

## Backups
- Automated backups on for every data store holding user data (RDS automated backups/snapshots at minimum daily, with a retention window matched to the project's recovery needs).
- Backups are encrypted (inherits the source's encryption-at-rest setting on RDS) and access to restore from them is as tightly scoped as access to production itself — a backup is a full copy of the data, not a lesser-protected asset.
- Test restoration periodically — an untested backup is a hope, not a control.

## Related canon
`references/security/secure-baseline.md` is the general bar; `references/security/payments-security.md` covers the restricted-tier case of payment data specifically; `references/security/secrets-management.md` covers credentials/keys (a different asset class from user PII, same protection discipline); `references/infra/aws.md` covers the RDS/S3 provisioning this doc assumes.
