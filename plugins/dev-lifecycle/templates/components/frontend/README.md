<!--
block: components/frontend                 # catalog component (shared pnpm workspace package @repo/web-shared)
needs:
  - shared workspace package: @repo/api-client (workspace:*) — generated hooks/models + the fetch mutator
  - peers from the app: react, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers (one instance each)
  - app wiring: configureApiClient({ baseUrl, cookieMode, getAccessToken }) + the QueryClientProvider/AuthProvider mount
  - a cookie-mode auth backend (references/wiring/auth-end-to-end.md)
exposes:
  - workspace package: @repo/web-shared — portable cookie-mode AuthProvider + guards, QueryClient factory, error/JWT/form helpers
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# @repo/web-shared

The shared React building blocks every **web** frontend imports on top of `@repo/api-client`: the cookie-mode `AuthProvider` + route guards, a `QueryClient` factory with auth-aware error handling, error/JWT helpers, and zod form helpers. Lives at `templates/components/frontend/` in this repo; scaffolding materializes it into `<project>/packages/web-shared/`, a sibling of `packages/api-client` under the same pnpm workspace (see "Materialized-location paths").

It is deliberately **framework-portable**: no `react-router`, no `import.meta`, and no `document`/`window` access at module top level anywhere in the package. That's what lets the *same* package import cleanly into a Vite SPA (Stage 6's app block) and into a Next.js client component (Stage 7) — the guards are render-gate primitives the app supplies its own router redirects to.

## Contents
- Composition contract
- What it is / isn't
- The export surface
- Wiring (what the app does)
- The cookie-mode auth lifecycle
- Portability constraints
- Dep vs peerDep
- Materialized-location paths
- Testing

## Composition contract

**NEEDS**
- **`@repo/api-client`** (`workspace:*`) — the generated hooks (`useLoginAuthLoginPost`, `useRefreshAuthRefreshPost`, `useLogoutAuthLogoutPost`, `useMeAuthMeGet`, `adminPingAdminPingGet`, …), the models (`ErrorEnvelope`/`ErrorCode`/`TokenResponse`/`PrincipalOut`), and the `configureApiClient` seam. The app must have run `just client-generate` so those tags exist; the `auth`/`admin` barrel exports landed in Stage 6.
- **Peer instances from the consumer** — `react`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`. One instance of each, owned by the app (see "Dep vs peerDep").
- **Runtime wiring by the app** — `configureApiClient({ baseUrl, cookieMode: true, getAccessToken })` once at startup, and the provider mount (see "Wiring"). This package does not call `configureApiClient` itself.
- **A cookie-mode auth backend** — the `/auth/login|refresh|logout|me` endpoints (cookie posture), at least one role-gated route (`/admin/ping`), and credentialed CORS naming the web origin. See `references/wiring/auth-end-to-end.md`.

**EXPOSES**
- **Workspace package `@repo/web-shared`** — import from its root (`index.ts`); it re-exports every public symbol. See "The export surface".
- **Its co-located doc fragment** — `docs/fragment.md`, aggregated into the project root README by `just docs-generate`.

## What it is / isn't
- **Is:** the portable web layer between `@repo/api-client` and a specific app — auth lifecycle, query defaults, error mapping, and form plumbing that every web frontend needs identically, written once so a Vite SPA and a Next.js app share it.
- **Isn't:** an app. It ships no routes, no pages, no styling system, and no router. The guards render `children` vs a `fallback` — the *app* decides what the fallback is (a redirect, a login prompt). It also isn't a place for API-calling code that belongs in `@repo/api-client`'s mutator.

## The export surface
Everything is a root export of `@repo/web-shared`:

| Area | Exports |
| --- | --- |
| **auth** | `AuthProvider` (+ `AuthProviderProps`), `useAuth`, `AuthContext`, `AuthContextValue`/`AuthState`, `RequireAuth`, `RequireRole`, `getAccessToken` |
| **query** | `createQueryClient` (+ `CreateQueryClientOptions`) |
| **errors** | `ApiError`, `isApiError`, `unwrap` (+ `ApiResult`), `isErrorEnvelope`, `getErrorCode`, `errorCodeToMessage`, `ApiErrorBoundary` |
| **jwt** | `decodeAccessTokenClaims` (+ `AccessTokenClaims`) |
| **forms** | `useZodForm`, `FieldError`, `applyEnvelopeToForm` |

Two seams matter most for wiring:
- **`getAccessToken`** — the getter the app passes to `configureApiClient({ getAccessToken })`. `AuthProvider` keeps the in-memory access token behind it; the mutator injects it as `Authorization: Bearer …` on every generated call.
- **`unwrap`** — wrap a generated call in your `queryFn`/`mutationFn` (`unwrap(await meAuthMeGet())`) so orval's "401-resolves-as-data" becomes a thrown `ApiError`. Without it, react-query never sees a 401 as an error and the 401 → refresh flow can't fire.

## Wiring (what the app does)
`AuthProvider` must be mounted **inside** a `QueryClientProvider` (it uses the generated hooks). One-time startup wiring:

```ts
// apps/web/src/main.tsx (Vite) — before rendering
import { configureApiClient } from "@repo/api-client";
import { getAccessToken } from "@repo/web-shared";
configureApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  cookieMode: true,   // web posture (refresh token in an HttpOnly cookie)
  getAccessToken,     // the AuthProvider's in-memory access token
});
```

```tsx
// The provider tree
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, createQueryClient } from "@repo/web-shared";

const queryClient = createQueryClient(); // no-retry-on-401/403 + auth-aware onError

export const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider onAuthExpired={() => router.navigate("/login")}>
      {/* routes; guards get router redirects as their `fallback` */}
    </AuthProvider>
  </QueryClientProvider>
);
```

The guards never navigate — the app supplies the redirect:

```tsx
<RequireRole role="admin" fallback={<Navigate to="/" replace />}>
  <AdminPage />
</RequireRole>
```

Next.js (Stage 7): identical, but the wiring lives in a `"use client"` module — this package intentionally omits its own `"use client"` directive so the consumer owns that boundary, and reads `process.env.NEXT_PUBLIC_API_BASE_URL` instead of `import.meta.env`.

## The cookie-mode auth lifecycle
`AuthProvider` implements `references/wiring/auth-end-to-end.md`'s web (cookie) flow verbatim:
- **Login** (`useLoginAuthLoginPost`) — cookie mode sends `X-Auth-Mode: cookie`; the access token is stored in React state **and** the module-scoped bridge `getAccessToken` reads; roles are decoded for UX gating; the empty-string body `refresh_token` is ignored. Nothing is ever written to `localStorage`/`sessionStorage`.
- **Refresh** — single-flight (`useRef` guard): a 401 from a non-auth call (surfaced via `unwrap` → `ApiError` → the `QueryClient`'s `onError`) drives one `useRefreshAuthRefreshPost`; the mutator echoes the `csrf_token` cookie as `X-CSRF-Token`. On success the rotated access token replaces the old one and `invalidateQueries()` retries the failed call with it.
- **Refresh failure** — a 401 on the refresh itself (reuse-detected/expired family) clears in-memory auth and fires `onAuthExpired` (the app redirects to login).
- **Logout** (`useLogoutAuthLogoutPost`) — best-effort server call, then clears the in-memory token and `queryClient.clear()`.

`createQueryClient` supplies the other half: **no retry on 401/403**, and a `QueryCache`/`MutationCache` `onError` that drives the refresh (default) and runs any injected `onAuthExpired`. `decodeAccessTokenClaims` is **UX-only** (no signature check — the server's 403 is the real gate).

## Portability constraints
Enforced by the "no router / no bundler globals / no SSR-unsafe module-load" rule:
- **No `react-router`** — the guards are render-gates; the app owns navigation.
- **No `import.meta` / `process.env`** in this package — `baseUrl` comes via `configureApiClient` in the app, per framework.
- **No top-level `document`/`window`** — `decodeAccessTokenClaims` calls `atob`/`TextDecoder` *inside* the function; the in-memory token bridge is plain module state that is `null` on a server render, so `getAccessToken()` injects nothing there.

## Dep vs peerDep
`react`, `@tanstack/react-query`, `react-hook-form`, `zod`, and `@hookform/resolvers` are **peerDependencies** (pinned again as `devDependencies` for this package's own build/lint/test), for the same reason `@repo/api-client` makes react/react-query peers: hooks, a single `QueryClient`, and RHF's `FormProvider` context all require exactly one instance in the consumer's tree. `@repo/api-client` is a real (`workspace:*`) **dependency** — this package is a layer on top of it, not a peer of it. All version lines follow `references/compatibility-matrix.md` (Frontend/web + Frontend testing), not independent bumps.

## Materialized-location paths
`tsconfig.json`'s `extends` and `eslint.config.mjs`'s import of the root config are written as `../../<file>` — correct for the **materialized** location (`<project>/packages/web-shared/`, two levels below the project root), exactly as `@repo/api-client` does it. Don't "fix" them to be firm-plugins-relative. `tsconfig.json` also overrides the base's `NodeNext` module resolution to `bundler` (this package is consumed by Vite/Metro/Next bundlers, and its imports — like the generated client's — are extensionless), and `tsconfig.build.json` excludes `*.test.tsx` so `dist/` ships no test files while `typecheck` still checks them.

## Testing
`pnpm run test` runs `vitest run` under a jsdom environment (`vitest.config.ts`) with `@testing-library/react` and **MSW** (`setupServer`) intercepting the api-client mutator's `fetch` at the network boundary — the real data-fetching path, per `references/testing/frontend-testing.md`. The suite proves the load-bearing behavior: login sends `X-Auth-Mode: cookie`, stores the token, and surfaces the `/auth/me` principal; a 401 from a non-auth call triggers exactly one refresh (with the `X-CSRF-Token` echo) and the call retries with the rotated token; a refresh-401 clears auth and fires `onAuthExpired`; `RequireRole` renders vs its fallback off a decoded `roles` claim; `applyEnvelopeToForm` maps a 422; and `ApiErrorBoundary` catches an `ApiError`.
