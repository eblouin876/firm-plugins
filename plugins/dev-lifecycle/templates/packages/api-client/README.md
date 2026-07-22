<!--
block: packages/api-client                # catalog component (shared pnpm workspace package), not an app-level block
needs:
  - env var: API_BASE_URL — the backend origin the mutator prepends to every generated request path (unset resolves to "", i.e. relative URLs against a same-origin dev proxy)
  - shared workspace package consumers: any app importing @repo/api-client (web, mobile) must supply react + @tanstack/react-query themselves (peer dependencies, see "Dep vs peerDep" below)
exposes:
  - workspace package: @repo/api-client — typed React Query hooks + models generated from an OpenAPI schema
  - its co-located doc fragment (this file)
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# @repo/api-client

The shared typed API client every frontend/mobile block imports instead of hand-writing `fetch` calls. It is a generated package: React Query hooks and models produced by [orval](https://orval.dev) from an OpenAPI 3.1 schema, layered on a small hand-written `fetch` mutator (`src/mutator.ts`) — no axios. Lives at `templates/packages/api-client/` in this repo; scaffolding materializes it into `<project>/packages/api-client/`, a sibling of `apps/*` under the same pnpm workspace (see the "Materialized-location paths" note below — it affects `tsconfig.json` and `eslint.config.mjs`).

## Contents
- Composition contract (v0)
- What it is / isn't
- How `client-generate` works
- The mutator's response shape
- Dep vs peerDep
- Materialized-location paths
- Stage 3: swapping in the live schema
- Testing

## Composition contract (v0)

**NEEDS**
- **Env vars** — `API_BASE_URL`: the backend origin prepended to every request path by `src/mutator.ts`. Unset resolves to `""` (relative URLs against a same-origin dev proxy); a real deployment always sets it.
- **Shared workspace packages** — none; this package has no internal workspace dependencies. It is depended *on*, not a dependent.
- **From consumers** — any app importing this package supplies its own `react` and `@tanstack/react-query` instances (peer dependencies — see "Dep vs peerDep").

**EXPOSES**
- **Workspace package** `@repo/api-client` — import hooks/types from its root export (`index.ts`), not by deep-importing `src/generated/*` (those paths are `client-generate` output and reshuffle across regenerations).
- **Its generated contract** — the hooks, request/response types, and models mirror whatever OpenAPI schema `orval.config.ts`'s `input.target` currently points at (the sample fixture today; the live backend schema from Stage 3 on).

## What it is / isn't
- **Is:** the one typed client web and mobile both import, so request/response types are the API contract rather than hand-copied interfaces that drift (see `references/frontend/typescript.md`, "Types from a single source of truth").
- **Isn't:** a place to hand-write API-calling code. Everything under `src/generated/` is regenerated wholesale (`clean: true` in `orval.config.ts`) — edits there are lost on the next `client-generate`. Add hand-written logic (interceptors, retry policy, auth headers) to `src/mutator.ts` or a thin wrapper in `src/index.ts` instead.

## How `client-generate` works
`just client-generate` runs `pnpm --filter @repo/api-client run generate`, which runs `orval --config orval.config.ts`. Orval mode is `tags-split` + `client: 'react-query'` + `httpClient: 'fetch'`, with a custom mutator override pointing at `src/mutator.ts`'s `customFetch`. Output:
- `src/generated/models/` — one file per OpenAPI schema, plus a barrel `index.ts`.
- `src/generated/endpoints/<tag>/` — one file per OpenAPI tag, exporting the raw async function, a React Query `*QueryOptions`/`*MutationOptions` builder, and the `use*` hook itself, per operation.

The generated output **is committed** (small, since the fixture is small) so a clean clone builds offline without an orval run. Regenerate after any schema change and commit the diff — don't hand-edit generated files.

## The mutator's response shape
Orval's `fetch` client mode expects the mutator to resolve `{ data, status, headers }`, not just the parsed body — the generated response types (e.g. a 201-vs-422 union) are discriminated on `.status`, so callers pattern-match on it instead of relying on a thrown error for a documented non-2xx response. `customFetch` in `src/mutator.ts` builds that shape; a rejected promise is reserved for what the OpenAPI contract can't describe — a network failure, not a 4xx/5xx the schema documents.

## Dep vs peerDep
`react` and `@tanstack/react-query` are **peerDependencies** here, pinned again as exact-ish `devDependencies` for this package's own build/lint/test. Rationale: this package is imported by both a web app and a mobile app, each with its own React tree and its own `QueryClient`. If this package declared `react`/`@tanstack/react-query` as regular `dependencies`, pnpm could resolve a second copy in a consumer whose own version differs even slightly — React's hook rules require exactly one `react` instance in the tree, and TanStack Query hooks require exactly one `QueryClient` provider matching the `@tanstack/react-query` instance the hooks were built against. Peer dependencies make the consumer supply (and own) that single instance; the `devDependencies` entries here exist only so this package's own `build`/`typecheck`/`lint`/`test` scripts have something to compile and test against locally.

## Materialized-location paths
`tsconfig.json`'s `extends` and `eslint.config.mjs`'s import of the root config are both written as `../../<file>` — correct for this package's **materialized** location (`<project>/packages/api-client/`, two levels below the project root), not for where this file sits inside `firm-plugins` (`templates/packages/api-client/`, a sibling of `templates/monorepo/`). Don't "fix" these to be firm-plugins-relative; they're intentionally scaffolding-relative. See the inline comment at the top of each file.

`tsconfig.json` also overrides the root's `module`/`moduleResolution` (`NodeNext`/`NodeNext`) to `ESNext`/`bundler`: this package is consumed by bundler-based apps (Vite for web, Metro for mobile) rather than executed directly under Node's ESM loader, and orval's generated imports don't carry the explicit `.js` extensions `NodeNext` resolution requires. `tsconfig.build.json` extends `tsconfig.json` and additionally excludes `*.test.ts`, so `pnpm run build`'s `dist/` doesn't ship test files while `pnpm run typecheck` still type-checks them.

## Stage 3: swapping in the live schema
`openapi.sample.json` is a **standalone stand-in** — a tiny (2-tag, 3-operation) OpenAPI 3.1 fixture shaped like FastAPI 0.139's actual output (the `anyOf`-nullable style on optional fields, the `HTTPValidationError`/`ValidationError` pair FastAPI emits for 422s), so `client-generate` produces realistic hooks without a running backend. Stage 3 (backend block lands, epic #22) points `orval.config.ts`'s `input.target` at the live backend's `/openapi.json` (or a build-time-exported copy of it) instead of this file — the generated output's shape changes to match, but the `client-generate` recipe, the mutator, and everything consumers import from `src/index.ts` stay the same.

## Testing
`pnpm run test` runs `vitest run` against `src/mutator.test.ts` — a smoke test of the mutator's request/response handling (JSON body parsing, the `{data, status, headers}` shape, default-`Content-Type` merging) using a stubbed global `fetch`. It does not exercise the generated hooks themselves (those are orval's output, not this package's logic to test) — a consuming app's component tests are where hook usage gets covered, per `references/testing/frontend-testing.md`.
