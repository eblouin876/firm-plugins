---
name: "data"
description: "Create consistent seed/fixture data and build reporting for a project — realistic development/demo/test data, and the queries, exports, or dashboards that answer questions about the app's data. Use this skill WHENEVER the work is about populating or reporting on data rather than building features: \"seed the database\", \"make some realistic test data\", \"set up fixtures\", \"build a report for X\", \"export this data\", \"add a dashboard/metrics\", \"how many users did Y\". It reuses the project's models and factories so seeding is consistent, and pushes reporting work into the database. It keeps seeding and reporting done the same way across every project."
---

# Data (seed & reporting)

Two related jobs, done consistently across projects: **seed data** (realistic dev/demo/test data) and **reporting** (the queries, exports, and metrics that answer questions about the app's data). Doing both the same way everywhere means a seed script or a report in one project reads like another.

## Core rules

- **Realistic, consistent, safe seed data.** Seeds mirror real shapes and relationships (not lorem ipsum), respect DB constraints and foreign keys, are **deterministic where tests depend on them**, and are layered by purpose. **Never put real PII or secrets in seed data.**
- **Seed through the project's factories, not hand-assembled dicts.** Reuse the same factories/models the `testing` skill uses — one source of truth for how an entity is built (see `${CLAUDE_PLUGIN_ROOT}/references/testing/backend-testing.md`). Copy-pasted data dictionaries drift and break when models change.
- **Reporting pushes work to the database.** Aggregate, filter, and sort in SQL / the ORM, parameterized — not by pulling whole tables into Python. Bound and paginate; index for the query patterns. See `${CLAUDE_PLUGIN_ROOT}/references/backend/sqlalchemy.md`, `postgres.md`, or `django.md`.
- **Don't leak.** Reports and exports exclude secrets and unnecessary PII; scope each to exactly what the consumer needs.
- **Consistency across projects.** Same seeding and reporting patterns everywhere — idempotent seed scripts, standard export formats, testable reports.
- **Work context-efficiently.** Read the models and existing factories/reports, not the whole codebase (`${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).

## Workflow

### 1. Detect models & existing setup
Read the schema/models, existing factories and seed scripts, and any current reporting. Conform to what's there rather than inventing a parallel approach.

### 2. Seed data (when that's the job)
Decide the **layers** needed and build each through the project's factories, idempotently:
- **Dev seed** — the minimal realistic data to run the app locally.
- **Demo dataset** — a richer, believable dataset for showing the product.
- **Test fixtures** — deterministic data the test suite relies on.
Respect constraints and relationships so the data is valid; keep it reproducible (seeded randomness). Make the seed script safe to re-run.

### 3. Reporting (when that's the job)
Define the question first, then write the query pushing aggregation into the database, parameterized and bounded. Choose the output deliberately — a CSV/JSON/xlsx export, a JSON endpoint, or a scheduled job — and exclude sensitive fields. Confirm the supporting index exists for the query pattern.

### 4. Verify
Seeds load cleanly and idempotently and produce valid, realistic data. Reports return the **correct numbers on known data** — test a report like code (a known fixture → an expected result), so it can't silently drift.

### 5. Hand off
What seeds and reports now exist, how to run them, the output format, and any data-safety notes (what's excluded and why).

## What this skill does NOT do
- Put real PII or secrets into seed data.
- Hand-assemble data instead of using the project's factories.
- Compute in Python what the database should aggregate (pull whole tables into memory).
- Leak sensitive fields in a report or export.
- Build analytics *infrastructure* (warehouses, pipelines) — that's `infrastructure`/`devops`; this is app-level seed and reporting.
