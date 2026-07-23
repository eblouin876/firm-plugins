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

**STUB — sub-agent D finalizes this README and adds `docs/fragment.md`.** This
sub-agent (A) built the scaffold, provider wiring, and the public SSR landing
page only; sub-agent B adds the auth/admin route groups and tests.

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
- The dev cross-origin cookie fix
- SSR-auth posture
- Not yet built (sub-agents B / D)

## Composition contract

**NEEDS**
- **`@repo/api-client`** (`workspace:*`) — the generated hooks, models, and `configureApiClient`, called once in `app/providers.tsx`.
- **`@repo/web-shared`** (`workspace:*`) — `AuthProvider`, `RequireAuth`/`RequireRole` guards, `createQueryClient`, `getAccessToken`, `unwrap`/`ApiError`, `useZodForm`/`applyEnvelopeToForm`. Same portable package the Vite SPA consumes — it has no router dependency, so it imports cleanly here too.
- **App dependencies** — `react`, `react-dom`, `next`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `tailwindcss` + `@tailwindcss/postcss`. One instance each; all pinned via `references/compatibility-matrix.md`.
- **`NEXT_PUBLIC_API_BASE_URL`** — the PUBLIC backend origin (empty in dev; see the cookie fix below). A URL, never a secret — `NEXT_PUBLIC_`-prefixed vars are inlined into the browser bundle.
- **A cookie-mode auth backend** — the `/auth/*` endpoints + a role-gated route (`/admin/ping`), reached same-origin (dev rewrites / prod edge routing) or via credentialed CORS.

**EXPOSES**
- **`apps/web`** — the Next.js app: `next build` → `.next/standalone` (the minimal traced server, what the Dockerfile ships) plus `.next/static`; statically-rendered public routes (`app/page.tsx`) and client-rendered authenticated routes (sub-agent B). It is an app, not an importable package.
- **Its co-located doc fragment** — `docs/fragment.md` (added by sub-agent D), aggregated into the project root README by `just docs-generate`.

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

## The dev cross-origin cookie fix
Cookie-mode auth keeps the refresh token in a `SameSite=Lax` `HttpOnly`
cookie, which the browser only attaches on **same-site** requests. So
`next.config.ts`'s `async rewrites()` forwards the same API path list the
SPA's `vite.config.ts` proxy uses (`/auth`, `/admin`, `/items`, `/health`,
`/readyz`) to `NEXT_DEV_API_PROXY ?? "http://localhost:8000"`, and dev sets
`NEXT_PUBLIC_API_BASE_URL=""` so the client issues same-origin relative URLs
through that rewrite — one origin, cookies attach, no `Secure` needed on
localhost.

## SSR-auth posture
Client-auth for app surfaces, SSR for public pages. `app/page.tsx` is a
server component with no auth check and no client-auth bundle — the honest
SSR win over the SPA, where every route ships the same JS regardless of
whether it needs auth. Authenticated screens (sub-agent B's `(app)` route
group) stay client-rendered, same posture as the SPA — full details land in
`docs/fragment.md` (sub-agent D).

## Not yet built (sub-agents B / D)
- The `(app)` / `(auth)` route groups, the auth/admin screens, and tests — sub-agent B.
- `docs/fragment.md`, the remaining README sections (Screens, Build & deploy, Testing, Materialized-location paths, Secrets), and folding this block's rows into the root doc-fragment aggregation — sub-agent D.
