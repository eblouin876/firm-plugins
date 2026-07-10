<!--
library: pydantic
versions-covered: "1.x, 2.x"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://docs.pydantic.dev
-->

# Pydantic conventions

Granular guidance for Pydantic models — request/response schemas, validation, and settings. Read whenever the work touches data models at the boundary. Used by FastAPI (see `fastapi.md`) but also anywhere validation happens. Subordinate to the project's existing conventions.

## Version check (do this first)
**Pydantic v1 vs v2 is decisive — they are effectively different libraries.** Confirm the installed major from the lockfile and write for it; don't mix idioms.

- **Pydantic v2** (modern default; FastAPI requires >=2.x): config via `model_config = ConfigDict(...)` (e.g. `from_attributes=True` replaces v1's `class Config: orm_mode = True`). Validators are `@field_validator` / `@model_validator` (not v1's `@validator` / `@root_validator`). Serialize/parse with `model_dump()` / `model_validate()` (not `.dict()` / `.parse_obj()`). Settings live in the separate `pydantic-settings` package (`BaseSettings` moved out of core). Validation is Rust-backed (pydantic-core) and fast.
- **Pydantic v1**: older `@validator`/`@root_validator` decorators and the `Config` class. Only if the project is pinned to v1 — don't write v2 APIs into it.

## Schema design
- Keep Pydantic schemas separate from ORM models — schemas describe the API contract; models describe storage. Never reuse a SQLAlchemy model as a request/response body.
- Use the base/create/update/read split: a base with shared fields, a `Create` (accepts inputs like a raw password), an `Update` (fields optional), and a `Read`/`Out` that **never** exposes secrets (hashed passwords, internal flags, tokens).
- Constrain at the field level: `Field(min_length=, max_length=, ge=, le=, pattern=)`, `EmailStr`, etc. In FastAPI these become automatic 422s with precise errors — no hand-rolled validation for what a constraint expresses.

## Validation
- Prefer field constraints and types over imperative checks. Reach for `@field_validator` (v2) only for logic a constraint can't express (cross-field rules → `@model_validator`).
- Validators should be pure and deterministic; raise `ValueError`/`AssertionError` with a clear message — Pydantic turns it into a structured error.
- Coerce deliberately: understand v2's strict vs lax mode for the types you accept; use `Strict` types or `strict=True` where silent coercion would hide bad input.

## Settings & secrets
- Configuration comes from `pydantic-settings` `BaseSettings` (v2): typed env-var loading, one settings object injected as a dependency. Never hardcode secrets; never log them.
- Give settings sensible types and validation so a misconfigured environment fails fast at startup, not deep in a request.

## Types as the single source of truth
- Derive, don't duplicate. A schema is a natural contract source: FastAPI generates OpenAPI from it, and the frontend can codegen TypeScript types from that OpenAPI (see `typescript.md`). One definition, propagated — not parallel hand-maintained types.
