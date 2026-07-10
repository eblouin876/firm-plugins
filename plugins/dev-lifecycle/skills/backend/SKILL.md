---
name: backend
description: Build, modify, or review backend APIs following modern best practices. Use this skill WHENEVER the work involves the server-side application layer — API endpoints, request/response schemas, business logic, database models, queries, migrations, authentication/authorization, or background jobs. Primary stack is FastAPI (Python) with SQLAlchemy and PostgreSQL (Django where server-rendered + HTMX fits), but it adapts to the project's actual stack. Trigger it for requests like "build an endpoint for X", "add an API route", "model this in the database", "write the migration", "wire up auth", or any backend task that follows a plan. Before writing code, this skill ALWAYS detects the project's stack and the exact library versions and conforms to what's already there.
---

# Backend

Build backend APIs that fit the project as it actually is. The two biggest sources of broken backend work are (1) assuming a library version and writing code for the wrong one — Pydantic v1 and v2 are not the same library, nor are SQLAlchemy 1.4 and 2.0 — and (2) treating security and data integrity as afterthoughts. This skill front-loads version detection and bakes correctness, security, and integrity into the build.

## Core rules

- **Detect before you build.** Never assume the framework or library versions. Read the project first (step 1). Pin down the majors that change how everything is written.
- **Conform, don't convert.** Match the project's existing structure, patterns, naming, and libraries. Don't introduce a new ORM, validation approach, or project layout into an existing app unprompted.
- **Validate at the boundary, trust nothing from the client.** Every request body, query param, and path param is validated by a schema before it touches business logic. The database enforces its own constraints regardless of what the API layer believes.
- **Security is built in, not reviewed in.** Parameterized queries / ORM (never string-built SQL), authn/authz on protected routes, secrets from config/env (never hardcoded, never logged), least-privilege, no sensitive data in responses or logs. The code-review skill double-checks this — but the backend skill writes it secure the first time.
- **Work context-efficiently.** Detect from manifests/lockfiles, not by reading the tree; read one or two representative files to learn house style, not the whole codebase; load only the reference(s) for the layer and libraries in play. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.
- **Implement against a plan when one exists.** Build to the plan from the planning skill or the user. If there's no plan and the work is non-trivial, say so and suggest planning first.

## Workflow

### 1. Detect the stack (always)
Inspect the project before writing anything. Read the **dependency manifest** and **lockfile** for: framework (FastAPI? Django?), the **Pydantic major** (v1 vs v2 — decisive), the **SQLAlchemy version** (1.4 vs 2.0 — decisive) or Django ORM, the DB driver (`asyncpg`/`psycopg`), migration tool (`alembic`), task queue, auth libs, and test runner. Note **sync vs async** and match it. Read the **project layout** and one or two representative files to mirror house style.

State what you found in a line, e.g. "FastAPI + Pydantic v2 + async SQLAlchemy 2.0 + asyncpg + Alembic + pytest — following those." If greenfield, default to the modern stack (FastAPI + Pydantic v2 + async SQLAlchemy 2.0 + Postgres + Alembic, or Django for server-rendered + HTMX).

### 2. Design the contract first
Settle the API contract before handlers: routes, methods, request/response schemas, status codes, error shapes. A clear contract is what lets the frontend skill build against it. Keep request/response schemas (Pydantic) separate from database models (SQLAlchemy/Django ORM).

### 3. Build
Load only the references for the libraries actually in play:
- **API layer (FastAPI):** `${CLAUDE_PLUGIN_ROOT}/references/backend/fastapi.md`; for schemas/validation/settings also `${CLAUDE_PLUGIN_ROOT}/references/backend/pydantic.md`.
- **Data layer (SQLAlchemy):** `${CLAUDE_PLUGIN_ROOT}/references/backend/sqlalchemy.md`; for Postgres-native specifics `${CLAUDE_PLUGIN_ROOT}/references/backend/postgres.md`.
- **Django:** `${CLAUDE_PLUGIN_ROOT}/references/backend/django.md` (pairs with the frontend skill's HTMX path).
- If a significant library in the project has **no reference yet**, generate one from current official docs, use it now, and open a PR to add it to the plugin (see the onboarding/self-extend flow).

Expectations: match existing conventions; separate concerns (routing/validation → route layer, business logic → services, persistence → data layer); handle errors with correct status codes and non-leaky messages; type everything; every schema change gets a migration.

### 4. Hand off
Summarize what changed (routes, schemas, models, migrations) and state the API contract for new/changed endpoints so the frontend can build against it. Note migrations to run and anything left out of scope. The bar for merge-ready is `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`.

## What this skill does NOT do
- Assume a framework/library version without checking — especially Pydantic and SQLAlchemy/Django majors.
- Introduce a new ORM, validation library, or project structure into an existing app unprompted.
- Build the frontend/UI (that's the frontend skill — this skill defines the API the frontend consumes).
- Write string-interpolated SQL, hardcode secrets, skip authz on protected routes, or skip migrations.
