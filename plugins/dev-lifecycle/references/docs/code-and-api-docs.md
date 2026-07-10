<!--
library: documentation
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Code & API docs (docstrings, comments, API reference)

Guidance for documentation that lives with the code and for API references. Read after deciding which artifact you're writing. The project's existing conventions override anything here.

## Contents
- Comments: the why, not the what
- Docstrings (Python)
- JSDoc / TS
- API documentation

## Comments: the why, not the what
- A good comment explains **why** — intent, a non-obvious constraint, why the straightforward approach was avoided, a link to an issue/spec, a warning about a subtlety. It tells the reader something the code can't.
- A bad comment restates the code (`# increment i by 1`). Delete these; they add noise and rot into lies when the code changes.
- Prefer making the code self-explanatory (clear names, small functions) over compensating with comments. Comment what remains genuinely surprising.
- Keep comments next to what they describe and update them with the code. A `TODO`/`FIXME` should say what and ideally link a tracking item.
- Don't leave commented-out code in committed files — version control already remembers it.

## Docstrings (Python)
- Match the project's docstring style (Google, NumPy, or reStructuredText) — don't mix styles within a project.
- Document the **public** surface: modules, public classes, and functions whose behavior isn't obvious from the signature. Cover purpose, parameters, return value, and exceptions raised — but don't pad trivial functions whose name and types already say everything.
- Let type hints carry type information; the docstring carries meaning, units, constraints, and behavior (e.g. "raises `ValueError` if `amount` is negative", "timeout in seconds").
- For FastAPI, docstrings and field descriptions feed the generated OpenAPI docs — write them with the API reader in mind (see below).

## JSDoc / TS
- In TypeScript, let the types document shape; reserve comments/JSDoc for intent and non-obvious behavior. Avoid restating types in prose.
- Document exported functions, hooks, and components whose usage isn't self-evident — props meaning, side effects, gotchas. Skip ceremony on trivial components.

## API documentation
For an HTTP API, the reader wants to know how to call it correctly and what they'll get back.

- **Generated reference (FastAPI/OpenAPI):** FastAPI produces interactive OpenAPI docs from your routes, Pydantic schemas, status codes, and descriptions. Maximize this for free by: setting `response_model`s, adding `summary`/`description` to routes, `Field(description=...)` on schema fields, declaring status codes, tagging routes, and providing example values. This keeps the reference in sync with the code automatically — favor it over hand-maintained endpoint tables that drift.
- **Narrative API docs** (what generation can't convey): authentication (how to get and pass a token), error model and status-code conventions, pagination/filtering conventions, rate limits, versioning, and end-to-end examples of common flows. Show real request/response examples (`curl` or a client snippet) with realistic values.
- Document the **contract**, not the implementation — what the endpoint accepts and returns, not how it's wired internally. This is the same contract the backend skill hands to the frontend skill; keep it the single source of truth.
- Keep error documentation honest: list the status codes a caller should actually handle and what triggers them.
