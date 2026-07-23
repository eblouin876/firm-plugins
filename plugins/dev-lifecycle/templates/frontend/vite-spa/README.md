<!--
block: frontend/vite-spa
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
needs:
  - shared workspace package: @repo/api-client (workspace:*) — generated hooks/models + the fetch mutator (configured once at startup)
  - shared workspace package: @repo/web-shared (workspace:*) — AuthProvider, route guards, createQueryClient, unwrap/ApiError, useZodForm/applyEnvelopeToForm
  - app deps (one instance each, per the matrix): react, react-dom, react-router 7, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers, @headlessui/react, tailwindcss + @tailwindcss/vite, @vitejs/plugin-react
  - env: VITE_API_BASE_URL (PUBLIC — empty in dev; a URL, never a secret)
  - a cookie-mode auth backend origin — same-origin dev proxy, edge-routed or credentialed-CORS in prod (references/wiring/auth-end-to-end.md)
exposes:
  - app: apps/web — the built static SPA (content-hashed dist/ + index.html) and, secondarily, a non-root static-serve container (Dockerfile)
  - its co-located doc fragment: docs/fragment.md
-->

# Vite SPA app (`apps/web`)

The React single-page app block: **React 19 + Vite 8 + TypeScript 6**, routed
with **react-router v7** (library mode — `createBrowserRouter` +
`RouterProvider`), styled with **Tailwind v4 + Headless UI**, forms via
`@repo/web-shared`'s `useZodForm`. It is the web consumer of `@repo/api-client`
(in cookie mode) and `@repo/web-shared` (the portable auth/query/forms layer).
Lives at `templates/frontend/vite-spa/` in this repo; scaffolding materializes
it into `<project>/apps/web/`, a workspace member alongside `packages/*`.
Everything here is **subordinate to a project's existing conventions** — when a
scaffolded project has diverged, the project wins.

## Contents
- Composition contract
- What it is / isn't
- Provider wiring (main.tsx)
- Routing + guards
- The dev cross-origin cookie fix
- Screens
- Styling (Tailwind v4 + tokens)
- Build & deploy
- Testing
- Materialized-location paths

## Composition contract

**NEEDS**
- **`@repo/api-client`** (`workspace:*`) — the generated hooks (`useLoginAuthLoginPost`, `useMeAuthMeGet`, `adminPingAdminPingGet`, …), models, and `configureApiClient`. The app calls `configureApiClient` once at startup (see "Provider wiring").
- **`@repo/web-shared`** (`workspace:*`) — `AuthProvider`, `RequireAuth`/`RequireRole` guards, `createQueryClient`, `getAccessToken`, `unwrap`/`ApiError`, `useZodForm`/`applyEnvelopeToForm`. This app supplies the router redirects the guards use as their `fallback`.
- **App dependencies** — `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `tailwindcss` + `@tailwindcss/vite`, `@vitejs/plugin-react`. One instance each; all pinned via `references/compatibility-matrix.md`.
- **`VITE_API_BASE_URL`** — the PUBLIC backend origin (empty in dev; see the cookie fix below). A URL, never a secret — `VITE_`-prefixed vars are inlined into the browser bundle.
- **A cookie-mode auth backend** — the `/auth/*` endpoints + a role-gated route (`/admin/ping`), reached same-origin (dev proxy / prod edge routing) or via credentialed CORS. See `references/wiring/auth-end-to-end.md`.

**EXPOSES**
- **`apps/web`** — the built static SPA: `vite build` → `dist/` (content-hashed assets + `index.html`), plus a secondary non-root static-serve container (`Dockerfile`). It is an app, not an importable package.
- **Its co-located doc fragment** — `docs/fragment.md`, aggregated into the project root README by `just docs-generate`.

## What it is / isn't
- **Is:** the app shell — provider wiring, the route table, the auth/admin screens, and the styling entry. Routing lives HERE (react-router), never in `@repo/web-shared`, which stays router-agnostic so it also imports into a Next.js client component.
- **Isn't:** a home for portable auth/query/forms logic (that's `@repo/web-shared`) or API-calling code (that's `@repo/api-client`'s mutator). The app composes those; it doesn't re-implement them.

## Provider wiring (`src/main.tsx`)
The exact startup sequence, in order (see `references/wiring/auth-end-to-end.md`
and `@repo/web-shared`'s README):

1. `configureApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? "", cookieMode: true, getAccessToken })` — `getAccessToken` imported from `@repo/web-shared` so the in-memory access token rides every generated call as `Authorization: Bearer`.
2. `const queryClient = createQueryClient()` — the kit's auth-aware client (no retry on 401/403; a 401 drives the single-flight refresh).
3. Mount `<QueryClientProvider><AuthProvider onAuthExpired={() => router.navigate("/login")}><RouterProvider router={router} /></AuthProvider></QueryClientProvider>` — **AuthProvider MUST sit inside QueryClientProvider** (it uses the generated hooks); RouterProvider sits inside AuthProvider so every route can `useAuth()`.

Every generated call the app makes in a `queryFn`/`mutationFn` is wrapped in
`unwrap(...)` (e.g. the admin ping, the register/verify/reset mutations), so a
documented non-2xx throws an `ApiError` — which is what lets react-query treat a
401 as an error and drive the refresh flow. Login goes through
`useAuth().login`, which owns the in-memory token.

## Routing + guards
`src/router.tsx` is the `createBrowserRouter` table. Public auth routes render
standalone; the authenticated branch is a layout route whose element is
`<ProtectedRoute><App/></ProtectedRoute>`, with `/admin` additionally wrapped in
`<AdminRoute>`. `ProtectedRoute` / `AdminRoute` (`src/routes/`) are **thin
adapters** over web-shared's render-gate guards — they supply a react-router
`<Navigate>` as the `fallback` (`RequireAuth` → `/login`, `RequireRole "admin"`
→ `/`). The client gate is UX only; the server's 401/403 is the real gate (the
admin screen renders both the success and the 403 branch to make that explicit).

## The dev cross-origin cookie fix
Cookie-mode auth keeps the refresh token in a `SameSite=Lax` `HttpOnly` cookie,
which the browser only attaches on **same-site** requests. So `vite.config.ts`'s
`server.proxy` forwards the API paths (`/auth`, `/admin`, `/items`, `/health`,
`/readyz`) to the compose backend, and dev sets `VITE_API_BASE_URL=""` so the
client issues same-origin relative URLs through that proxy — one origin, cookies
attach, no `Secure` needed on localhost. Production keeps the browser
same-origin via edge routing, or uses explicit-origin credentialed CORS with
`Secure` cookies (see `docs/fragment.md`'s Deployment section and
`.env.example`).

## Screens
`src/routes/` — `login`, `register`, `verify-email` (consumes the emailed
token), `forgot-password` (request reset), `reset-password`, a `dashboard`
(authenticated landing showing the `/auth/me` principal + decoded roles), and
`admin` (renders the role-gated `/admin/ping`). All forms use `useZodForm` +
Headless UI primitives, map a 422 with `applyEnvelopeToForm`, and mirror the
backend's anti-enumeration posture (generic login/reset messages).

## Styling (Tailwind v4 + tokens)
Tailwind v4 CSS-first: `src/styles/index.css` is the single entry
(`@import "tailwindcss"`), and `src/styles/theme.css` is the `@theme` token seam
(`--color-*` / `--radius-*`) the `design-system` skill owns later. Components
reference tokens through utilities (`bg-primary`, `text-muted`, `rounded-md`),
never raw hex/px. `@tailwindcss/vite` is wired in `vite.config.ts` (not the
legacy PostCSS path).

## Build & deploy
`vite build` → `dist/` (hashed assets + `index.html`). Host on any static/CDN
target with SPA history fallback (unknown path → `/index.html` 200). A secondary
multi-stage `Dockerfile` (build on the matrix's `node:24-bookworm-slim`, final
stage a **non-root** zero-dependency static server that does the SPA fallback,
no secret baked — only the public `VITE_API_BASE_URL`) is provided; build it
from the project root (`docker build -f apps/web/Dockerfile -t web .`). No root
`justfile` edits — the app participates in `just dev/build/lint/typecheck/test`
via its own `package.json` scripts.

## Testing
`pnpm --filter web test` runs `vitest run` under jsdom with
`@testing-library/react` + **MSW** (`setupServer`) intercepting the api-client
mutator's fetch. It includes a route-level component test and the load-bearing
**"login end-to-end via the shared client"** integration test: it renders the
real `AuthProvider` + login screen wired to the REAL `@repo/api-client` hooks,
MSW stubs `POST /auth/login` → a `TokenResponse` with a roles JWT +
`refresh_token: ""` (and sets `csrf_token` via `document.cookie`) and
`GET /auth/me` → the principal, then asserts the authenticated principal renders
and a subsequent protected call (`GET /admin/ping`) carries
`Authorization: Bearer`.

## Materialized-location paths
`tsconfig.json`'s `extends` and `eslint.config.mjs`'s import of the root config
are written as `../../<file>` — correct for the **materialized** location
(`<project>/apps/web/`, two levels below the project root), exactly as
`@repo/api-client` and `@repo/web-shared` do it. Don't "fix" them to be
firm-plugins-relative. `tsconfig.json` also overrides the base's `NodeNext`
module resolution to `bundler` (this app is Vite-bundled and imports the
extensionless workspace-package builds) and sets `noEmit` (Vite owns the bundle;
tsc is a pure typechecker here).
