<!--
block: frontend/nextjs
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
needs:
  - shared workspace package: @repo/api-client (workspace:*) — generated hooks/models + the fetch mutator (configured once at startup)
  - shared workspace package: @repo/web-shared (workspace:*) — AuthProvider, route guards, createQueryClient, unwrap/ApiError, useZodForm/applyEnvelopeToForm
  - app deps (one instance each, per the matrix): react, react-dom, next, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers, @headlessui/react, tailwindcss + @tailwindcss/postcss
  - env: NEXT_PUBLIC_API_BASE_URL (PUBLIC — empty in dev; a URL, never a secret)
  - a cookie-mode auth backend origin — same-origin dev rewrites (next.config.ts), edge-routed or credentialed-CORS in prod (references/wiring/auth-end-to-end.md)
exposes:
  - app: apps/web — the Next.js (App Router) app: `.next/standalone` server output (Dockerfile) + statically-rendered public routes
  - its co-located doc fragment: docs/fragment.md
-->

# Next.js (App Router) app (`apps/web`)

The App Router counterpart to `templates/frontend/vite-spa/`: the same
`@repo/api-client` + `@repo/web-shared` provider wiring, translated to Next
idioms. **React 19 + Next.js 16 (Turbopack) + TypeScript 6**, styled with
**Tailwind v4** via `@tailwindcss/postcss` (Next's first-party integration,
not `@tailwindcss/vite`). Lives at `templates/frontend/nextjs/` in this repo;
scaffolding materializes it into `<project>/apps/web/`, a workspace member
alongside `packages/*` (mutually exclusive with the Vite SPA block — a
project picks one web app template, not both). Everything here is
**subordinate to a project's existing conventions** — when a scaffolded
project has diverged, the project wins.

## Contents
- Composition contract
- What it is / isn't
- Provider wiring (`app/providers.tsx`)
- Routing + guards
- The dev cross-origin cookie fix
- Screens
- Styling (Tailwind v4 + tokens)
- SSR-auth posture
- Build & deploy
- Testing
- Materialized-location paths

## Composition contract

**NEEDS**
- **`@repo/api-client`** (`workspace:*`) — the generated hooks, models, and `configureApiClient`, called once in `app/providers.tsx`.
- **`@repo/web-shared`** (`workspace:*`) — `AuthProvider`, `RequireAuth`/`RequireRole` guards, `createQueryClient`, `getAccessToken`, `unwrap`/`ApiError`, `useZodForm`/`applyEnvelopeToForm`. Same portable package the Vite SPA consumes — it has no router dependency, so it imports cleanly here too.
- **App dependencies** — `react`, `react-dom`, `next`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `tailwindcss` + `@tailwindcss/postcss`. One instance each; all pinned via `references/compatibility-matrix.md`.
- **`NEXT_PUBLIC_API_BASE_URL`** — the PUBLIC backend origin (empty in dev; see the cookie fix below). A URL, never a secret — `NEXT_PUBLIC_`-prefixed vars are inlined into the browser bundle.
- **A cookie-mode auth backend** — the `/auth/*` endpoints + a role-gated route (`/admin/ping`), reached same-origin (dev rewrites / prod edge routing) or via credentialed CORS.

**EXPOSES**
- **`apps/web`** — the Next.js app: `next build` → `.next/standalone` (the minimal traced server, what the Dockerfile ships) plus `.next/static`; statically-rendered public routes (`app/page.tsx`) and client-rendered authenticated routes (`app/(app)/*`). It is an app, not an importable package.
- **Its co-located doc fragment** — `docs/fragment.md`, aggregated into the project root README by `just docs-generate`.

## What it is / isn't
- **Is:** the app shell — provider wiring, the `app/` route tree, and the styling entry, following the same NEEDS/EXPOSES contract as `templates/frontend/vite-spa/`.
- **Isn't:** a home for portable auth/query/forms logic (that's `@repo/web-shared`, unchanged from the SPA) or API-calling code (that's `@repo/api-client`'s mutator, unchanged from the SPA).

## Provider wiring (`app/providers.tsx`)
`app/layout.tsx` is a **server component** — it renders the `<html>/<body>`
shell, imports `globals.css`, and wraps `{children}` in `<Providers>`.
`app/providers.tsx` is `"use client"` and does, in order:

1. `configureApiClient({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "", cookieMode: true, getAccessToken })` at **module scope** (not inside the component body) — the module-scope placement is what makes this run exactly once, the App Router analog of the SPA's `main.tsx` being a run-once entrypoint.
2. `const [queryClient] = useState(() => createQueryClient())` — deliberately per-mount and browser-only (not module scope), so no query cache leaks across concurrent server requests and the expiry listener doesn't double-register on remount.
3. Mount `<QueryClientProvider><AuthProvider onAuthExpired={() => router.push("/login")}>{children}</AuthProvider></QueryClientProvider>` — `router` from `next/navigation`'s `useRouter()`, the direct analog of the SPA's `router.navigate("/login")`.

## Routing + guards
No route table to write — the App Router derives routes from `app/`'s folder
structure. `app/(auth)/*` (login/register/verify-email/forgot-password/
reset-password) is a route group with an empty layout — the public auth
screens, each rendering its own centered `<AuthCard>`, no shell. `app/(app)/*`
(dashboard, admin) is the authenticated route group: its `layout.tsx` wraps
`{children}` in `<ProtectedGate>` (`components/auth/ProtectedGate.tsx`) and
renders the header/nav chrome. `components/auth/ProtectedGate.tsx` and
`components/auth/AdminGate.tsx` are **thin Next adapters** over web-shared's
router-agnostic `RequireAuth`/`RequireRole` render-gates — since the App
Router has no `<Navigate>`-style declarative redirect element (unlike
react-router, which the Vite SPA's `ProtectedRoute`/`AdminRoute` use), each
gate's `fallback` is a small component that fires `useRouter().replace(...)`
in an effect instead (`ProtectedGate` → `/login`, `AdminGate` → `/`). The
client gate is UX only; the server's 401/403 is the real gate (the admin
screen renders both the success and the 403 branch to make that explicit,
same as the SPA).

## The dev cross-origin cookie fix
Cookie-mode auth keeps the refresh token in a `SameSite=Lax` `HttpOnly`
cookie, which the browser only attaches on **same-site** requests. So
`next.config.ts`'s `async rewrites()` forwards the same API path list the
SPA's `vite.config.ts` proxy uses (`/auth`, `/admin`, `/items`, `/health`,
`/readyz`) to `NEXT_DEV_API_PROXY ?? "http://localhost:8000"`, and dev sets
`NEXT_PUBLIC_API_BASE_URL=""` so the client issues same-origin relative URLs
through that rewrite — one origin, cookies attach, no `Secure` needed on
localhost.

## Screens
`app/(auth)/*` — `login`, `register`, `verify-email` (consumes the emailed
token via `useSearchParams`), `forgot-password` (request reset),
`reset-password`. `app/(app)/*` — `dashboard` (authenticated landing showing
the `/auth/me` principal + decoded roles) and `admin` (renders the role-gated
`/admin/ping`). All forms use `useZodForm` + Headless UI primitives
(`components/form.tsx`), map a 422 with `applyEnvelopeToForm`, and mirror the
backend's anti-enumeration posture (generic login/reset messages) — byte-for-
byte the same screen behavior as the Vite SPA, just as Next pages instead of
react-router route elements.

## Styling (Tailwind v4 + tokens)
Tailwind v4 CSS-first: `app/globals.css` is the single entry
(`@import "tailwindcss"`), wired through `@tailwindcss/postcss`
(`postcss.config.mjs`) — Next's first-party integration, not a Vite plugin.
`app/theme.css` is the `@theme` token seam (`--color-*` / `--radius-*`) the
`design-system` skill owns later. Components reference tokens through
utilities (`bg-primary`, `text-muted`, `rounded-md`), never raw hex/px.

## SSR-auth posture
Client-auth for app surfaces, SSR for public pages. `app/page.tsx` is a
server component with no auth check and no client-auth bundle — the honest
SSR win over the SPA, where every route ships the same JS regardless of
whether it needs auth. Authenticated screens (the `(app)` route group) stay
client-rendered, same posture as the SPA. This app deliberately does **not**
validate the session server-side for authenticated routes (no middleware
reading a cookie to gate `/dashboard`) — the backend's refresh-token cookie is
`Path=/auth`-scoped, so the Next server process can't see it on a request to
a different path without a broader, deliberately out-of-scope cookie-scoping
redesign. See `docs/fragment.md`'s Deployment section for the full statement
of this tradeoff and its container-service (not static-upload) hosting
consequence.

## Build & deploy
`next build` → `.next/standalone` (a minimal, self-contained traced server —
`output: "standalone"` in `next.config.ts`) + `.next/static`. Unlike the Vite
SPA's static bundle, this needs a **Node runtime** in production (`next
start`, or the standalone server's own `server.js`) because the dev
rewrites/headers are server features with no static-hosting equivalent — so
this app is a **container service** for infra purposes, not an S3/CloudFront
upload. A multi-stage `Dockerfile` (build on the matrix's
`node:24-bookworm-slim`, runtime stage runs as the non-root `node` user, no
secret baked — only the public `NEXT_PUBLIC_API_BASE_URL`) ships the
production path; build it from the project root (the build context must see
the whole workspace, since this app imports `@repo/api-client` /
`@repo/web-shared`): `docker build -f apps/web/Dockerfile -t web .`. No root
`justfile` edits — the app participates in `just dev/build/lint/typecheck/test`
via its own `package.json` scripts.

## Testing
`pnpm --filter web test` runs `vitest run` (config: `vitest.config.ts`,
test-only — never read by `next build`/`next dev`) under jsdom with
`@testing-library/react` + **MSW** (`setupServer`) intercepting the
api-client mutator's fetch, and `next/navigation` mocked (`useRouter`,
`useSearchParams`) since there's no App Router test runtime to mount routes
in. It includes the public-landing component test (`app/page.test.tsx` —
proves the SSR/no-auth-provider split) and the load-bearing **"login
end-to-end via the shared client"** integration test
(`src/test/login-e2e.test.tsx`): it renders the real `AuthProvider` + the
real `LoginPage` wired to the REAL `@repo/api-client` hooks, MSW stubs `POST
/auth/login` → a `TokenResponse` with a roles JWT + `refresh_token: ""` (and
sets `csrf_token` via `document.cookie`), `GET /auth/me`, and `GET
/admin/ping`, then asserts: the login request carries `X-Auth-Mode: cookie`,
the access token is held in memory only, `router.replace("/dashboard")`
fires on success, the `/auth/me` call carries `Authorization: Bearer`, and —
once a small test-only two-screen harness swaps to the real `AdminPage` on
that redirect — the subsequent `/admin/ping` call carries the bearer too.

## Materialized-location paths
`tsconfig.json`'s `extends` and `eslint.config.mjs`'s import of the root
config are written as `../../<file>` — correct for the **materialized**
location (`<project>/apps/web/`, two levels below the project root), exactly
as `@repo/api-client`, `@repo/web-shared`, and the Vite SPA do it. Don't "fix"
them to be firm-plugins-relative. `tsconfig.json` also overrides the base's
`NodeNext` module resolution to `bundler` (Next/Turbopack bundles this app and
imports the extensionless workspace-package builds) and sets `noEmit` (Next
owns the bundle; tsc is a pure typechecker here). Its `include` covers
`app`/`components`/`src` (the last for the vitest suite); `next.config.ts` and
`vitest.config.ts`/`vitest.setup.ts` opt into ESLint's default-project parser
service instead, the same split the Vite SPA and `@repo/web-shared` use for
their own config files.
