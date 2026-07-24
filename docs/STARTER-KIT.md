# The starter kit — an index

A map of everything `dev-lifecycle` ships to compose a runnable monorepo, so you can find the piece you need without reading the whole `templates/`/`references/` tree. This doc is an index, not canon — every entry links to its real source of truth; when this list and that source disagree, the source wins.

---

## 1. What the starter kit is

Alongside the plugin's per-library reference library, `dev-lifecycle` ships a second, composable layer: golden-path template **blocks** and lighter catalog **components** that scaffolding stitches into an actual working monorepo, plus **feature recipes** that wire an existing block into one capability (Stripe, S3, auth, and so on). The decision to add this layer — and why it sits alongside references rather than replacing them — is recorded in [`docs/adr/0001-templates-recipes-monorepo-security-docs.md`](adr/0001-templates-recipes-monorepo-security-docs.md); read that for the rationale, not restated here.

## 2. The composition model

A scaffolded project starts from the **monorepo skeleton** (`plugins/dev-lifecycle/templates/monorepo/`) — a pnpm workspace with a standardized `justfile`, `docker-compose.yml`, and a root `README.md.tmpl` — and grows by composing in:

- **Blocks** (`templates/<layer>/<name>/`) — a backend, a frontend, a mobile app, infra — each declaring a composition contract (what it `needs` from the monorepo, what it `exposes`) so independently-authored blocks stitch together without knowing each other's internals.
- **Catalog components** (`templates/components/<domain>/`) — lighter drop-in slices (a Python mixin, a vendored security middleware, a shared frontend package) that blocks vendor or import.
- **Recipes** (`references/recipes/<name>.md`) — portable how-tos that wire an already-composed block/component into one feature, without inventing new infrastructure.

Every block, component, and recipe ships a **doc fragment** co-located with its own code (`docs/fragment.md` once materialized, or a recipe's own `## Doc fragment` section). `just docs-generate` (backed by `scripts/docs-aggregate.mjs` in the materialized project) aggregates every fragment into the scaffolded project's root README — the project's own docs stay true to its code because they're assembled from the code's own doc fragments, not hand-maintained separately. `just docs-check` fails CI on drift.

The full model — the doc fragment format, the root README's aggregation-marker regions, and the project `CLAUDE.md` template — is canon at [`references/authoring/documentation-standard.md`](../plugins/dev-lifecycle/references/authoring/documentation-standard.md). The composition-contract schema every block/component fills is canon at [`templates/_TEMPLATE-README.md`](../plugins/dev-lifecycle/templates/_TEMPLATE-README.md).

## 3. Blocks

Each block lives at `plugins/dev-lifecycle/templates/<layer>/<name>/` and declares a `needs`/`exposes` composition contract in its own `README.md` header. Backend blocks are alternatives (a project picks one); frontend/mobile/infra blocks compose alongside each other.

| Block | Materializes to | Needs (short) | Exposes (short) |
|---|---|---|---|
| `backend/fastapi` | `apps/api` | `DATABASE_URL`, `JWT_SIGNING_KEY` for `/auth/*`, Python 3.13 + uv | Item/auth/admin/blog/moderation routes, the OpenAPI 3.1 contract, security-composition wiring |
| `backend/django` | `apps/api` | `DATABASE_URL`, `SECRET_KEY`, Python 3.13 + uv — an **alternative** to `backend/fastapi` in the same slot | The DRF contract-emission layer (same routes as fastapi), `core/security/` middleware stack, `/api/schema` |
| `frontend/vite-spa` | `apps/web` | `@repo/api-client` + `@repo/web-shared`, `VITE_API_BASE_URL`, a cookie-mode auth backend | The built static SPA (`apps/web`), its doc fragment |
| `frontend/nextjs` | `apps/web` | Same as `vite-spa`, `NEXT_PUBLIC_API_BASE_URL` in place of the Vite env var | The Next.js App Router app (`.next/standalone` + statically-rendered public routes) |
| `frontend/nextjs-admin` | `apps/admin` | `@repo/api-client` + `@repo/web-shared`, the backend's `admin` role/claim, identical deps to `frontend/nextjs` | `apps/admin` — a SECOND, standalone Next.js app whole-app-gated on `admin`, its own container/subdomain |
| `mobile/expo` | `apps/mobile` | `EXPO_PUBLIC_API_BASE_URL`, `@repo/api-client` in bearer mode, `expo-secure-store` | An Expo Router React Native app wired to the standard `justfile` targets |
| `infra/aws-fargate` | `infra/aws-fargate` | A built + pushed app image, AWS OIDC credentials, ACM cert ARN(s), Terraform ~>1.15 | ECS Fargate service behind an HTTPS ALB, CloudFront static site, private RDS Postgres, Secrets Manager, a least-privilege OIDC deploy role |
| `packages/api-client` | `packages/api-client` | An OpenAPI 3.1 schema to generate from; consumers supply `react` + `@tanstack/react-query` as peers | `@repo/api-client` — typed React Query hooks/models (orval-generated) |

**The admin surface, in detail:** `frontend/nextjs-admin` is the `apps/admin` app — a second, standalone deployable, not bundled into `apps/web` — whole-app-gated on the backend's `admin` role. It drives three backend surfaces through `@repo/api-client`: user management at `/admin/users` (list/search/paginate, suspend/ban/reinstate/force-verify/edit-roles/delete), a moderation queue at `/admin/flags` (status-/target-type-filterable, resolve/dismiss), and a blog admin at `/admin/blog/*` (a TipTap WYSIWYG editor, posts list/create/edit/publish/unpublish/delete, comment hide/delete). Readers consume the same content anonymously through the backend's public `GET /blog/posts` (list) and `GET /blog/posts/{slug}` (detail) — no admin auth required. Every backend block sanitizes blog post HTML server-side with `nh3` (a Rust/`ammonia`-backed allowlist sanitizer) before it's ever persisted, so admin-authored rich text can never carry stored XSS to a public reader — see `templates/backend/fastapi/app/services/sanitize.py` / `templates/backend/django/core/services/sanitize.py`, byte-identical policies across both backend tracks.

## 4. Catalog components

Lighter drop-in slices at `plugins/dev-lifecycle/templates/components/<domain>/`, each with its own `needs`/`exposes` contract.

### Backend (`templates/components/backend/`)

| Component | What it provides |
|---|---|
| `db-mixins` | `Base`, `UUIDPrimaryKey`, `TimestampMixin`, `SoftDeleteMixin` — the SQLAlchemy declarative mixins every model composes |
| `db-session` | `configure_engine()`, `get_db()` — async SQLAlchemy engine/session setup and the `Depends(get_db)` FastAPI seam |
| `error-envelope` | `ErrorCode`, `ErrorEnvelope`, `AppError` + subclasses — the single `{error: {code, message, details?}}` contract every error maps to |
| `pagination` | `PageParams`, `Page[T]`, `paginate_select()` — the strict wire pagination envelope plus its SQLAlchemy query helper |
| `repository` | `AsyncRepository[ModelT]` — generic get/list/create/update/delete over an `AsyncSession`, soft-delete-aware |
| `settings` | `AppSettings` — the pydantic-settings base every project's own settings class extends |

### Frontend (`templates/components/frontend/`)

| Component | What it provides |
|---|---|
| `components/frontend` (`@repo/web-shared`) | The portable React layer every web frontend imports on top of `@repo/api-client`: cookie-mode `AuthProvider` + `RequireAuth`/`RequireRole` guards, a `QueryClient` factory, error/JWT helpers, zod form helpers. Materializes to `packages/web-shared` alongside `packages/api-client`. |

### Security (`templates/components/security/`)

| Component | What it provides |
|---|---|
| `audit-logging` | `audit_event()`, `redact()`, `bind_request_id()` — structured, redacted audit trail helpers |
| `auth` | `PasswordService`, `TokenService`, `AuthService` — password hashing (argon2), JWT mint/decode, register/login/refresh/logout, FastAPI + Django adapters |
| `cors-lockdown` | `CORSPolicy` — a framework-neutral explicit-allowlist CORS policy, FastAPI + Django wiring |
| `idempotency` | `IdempotencyStore` protocol + in-memory/Redis-stub implementations — safe request replay for mutating endpoints |
| `input-validation` | `StrictModel`, `SafeIdentifier`/`Slug`/`SafeText`/`Email` — hardened pydantic base model and reusable field types |
| `rate-limiting` | Token-bucket rate limiting — `BucketStore` protocol, FastAPI dependency/middleware, Django middleware |
| `secrets-loading` | `get_secret()`, `validate_required()` — a single typed secret accessor with an optional AWS Secrets Manager fallback |
| `security-headers` | `SecurityHeadersPolicy`, `DEFAULT_POLICY`, `CSPPolicy` — the response security-header middleware, FastAPI + Django |
| `webhook-signature` | `verify()`, `compute_signature()` — Stripe-style HMAC webhook signature verification with timestamp tolerance |

## 5. Recipes

Twelve feature recipes at `plugins/dev-lifecycle/references/recipes/`, plus `_RECIPE-TEMPLATE.md`, the schema exemplar `recipe-author` fills to add a new one.

| Recipe | What it wires |
|---|---|
| `audit-logging.md` | The `audit-logging` component into a feature's auth/admin/restricted-data actions |
| `background-jobs.md` | Celery + Redis (Django) or `BackgroundTasks` (FastAPI, light fire-and-forget) for async work off the request path |
| `caching.md` | Redis cache-aside — read-through, explicit TTL, write invalidation, leak-safe key naming |
| `data-export.md` | A streamed CSV/report export endpoint reusing an existing list endpoint's query and authorization scoping |
| `end-to-end-auth.md` | The `auth` component across backend (fastapi/django), web (cookie mode), and mobile (bearer mode) into one contract |
| `feature-flags.md` | Env-backed flags via `settings` for deploy-time toggles, plus a DB-backed table for redeploy-free flags, default-off |
| `file-upload-s3.md` | Direct-to-S3 upload via a server-minted presigned URL — the server never receives the file body |
| `push-notifications.md` | Expo push tokens + `expo-notifications` to a backend device-token registration endpoint and Expo's push service (a capability the kit doesn't ship yet — the recipe adds it) |
| `realtime-websockets.md` | FastAPI's native `WebSocket` endpoint, authenticated at handshake, with a Redis pub/sub fan-out path for multi-process deployments |
| `search.md` | PostgreSQL full-text search (`tsvector`/`tsquery` + GIN index) wired to an existing model and the `Page[T]` envelope |
| `stripe-payments.md` | Stripe Elements/Checkout to the kit's payments-security baseline — tokenized cards, verified webhooks, idempotent mutations, exact decimal money, full audit trail |
| `transactional-email.md` | The `auth` component's `EmailSender` abstraction for verification/reset mail and any other transactional send |

## 6. Wiring refs

Five cross-artifact wiring references at `plugins/dev-lifecycle/references/wiring/`, each documenting how two or more blocks/components agree at a seam that no single block's own README fully owns.

| Wiring ref | Covers |
|---|---|
| `api-client-generation.md` | Backend OpenAPI export → frozen `packages/api-client/openapi.json` → orval-generated TS client, consumed by web, admin, and mobile |
| `auth-end-to-end.md` | The `auth` component ↔ React web (cookie mode) ↔ Expo mobile (bearer mode) |
| `frontend-backend-contract.md` | CORS/cookie posture, public env-var conventions, the `ErrorEnvelope`/`ErrorCode` contract, and `Page[T]` pagination across `apps/web`, `apps/admin`, and the backend |
| `infra-app.md` | Backend/web/admin app templates ↔ `infra/aws-fargate` — `secret_store.py`'s process-env-first read path into Secrets Manager `valueFrom`, `/readyz` health checks, the deploy runbook |
| `mobile-backend.md` | The Expo app ↔ backend auth/account endpoints, bearer/SecureStore mode specifics |

## 7. Compatibility matrix

Every block, component, and recipe pins its versions to one keystone: [`references/compatibility-matrix.md`](../plugins/dev-lifecycle/references/compatibility-matrix.md). A block does not choose its own version of a kit-wide dependency — it cites the matrix (`versions-pinned-to`), and the matrix wins on disagreement. Bumping a matrix line is a deliberate, matrix-wide change (re-verify against official sources, update `last-verified`), never a per-block decision. Start there before touching any pinned version anywhere in the kit.

## 8. Standard task surface

Every runnable block wires into the project-root `justfile` (materialized from `templates/monorepo/justfile`) instead of inventing its own task runner. Targets are dash-named — `just` reserves `:` for the dependency separator:

| Target | Does |
|---|---|
| `install` | Installs the workspace (`pnpm install`), the entry point for a freshly scaffolded repo |
| `test` | Runs every workspace package's test script (`pnpm -r --if-present run test`) |
| `lint` | Lints every workspace package |
| `typecheck` | Type-checks every workspace package |
| `dev` | Runs every package's dev script in parallel, plus boots the API's Docker Compose stack if one is scaffolded in |
| `build` | Builds every workspace package |
| `deploy [env]` | Delegates to the `infra/aws-fargate` block's deploy script; fails loudly if that block isn't scaffolded in |
| `docs-generate` | Runs `scripts/docs-aggregate.mjs` to fold every block's `docs/fragment.md` into the root README |
| `docs-check` | Same, in `--check` mode — exits 1 on drift, the CI-friendly form |
| `client-generate` | Re-exports the backend's OpenAPI schema and regenerates `@repo/api-client` from it, so the committed schema and generated client never drift apart |
| `add-mobile` | Idempotently scaffolds `apps/mobile` from the `mobile/expo` block and runs `pnpm install` to register it |

## 9. How it stays fresh

Per [ADR 0001](adr/0001-templates-recipes-monorepo-security-docs.md), the plugin's freshness audit extends its remit from references alone to the whole starter kit: templates (blocks + catalog components), recipes, the compatibility matrix, and doc-fragment drift — staleness anywhere in the kit is caught the same way staleness in a reference is. Concretely, that remit covers:

- **References** — each reference's `versions-covered`/`last-verified` header checked against the library's current release.
- **Templates** — each block/component's `versions-pinned-to` + `last-verified` checked against the compatibility matrix and the block's own pinned dependencies.
- **Recipes** — each recipe's `applies-to` + `last-verified` checked against the blocks/components it wires.
- **The matrix** — `references/compatibility-matrix.md` itself checked against upstream releases, since every block/component/recipe pins to it.
- **Doc drift** — `just docs-check` (`scripts/docs-aggregate.mjs --check`) catching a scaffolded project's root README falling out of sync with its composed blocks' doc fragments.

None of this is a substitute for the hard merge gate: `python3 scripts/validate_plugin.py` runs in CI on every push and PR, checking the JSON manifests and every `SKILL.md`'s YAML frontmatter — the structural things Claude Code rejects on install. A freshness finding is a tracking issue for a reviewed PR; a `validate_plugin.py` failure blocks the merge outright.
