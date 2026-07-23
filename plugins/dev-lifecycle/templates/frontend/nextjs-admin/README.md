<!--
block: frontend/nextjs-admin
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
needs:
  - shared workspace package: @repo/api-client (workspace:*) — generated hooks/models + the fetch mutator (configured once at startup)
  - shared workspace package: @repo/web-shared (workspace:*) — AuthProvider, RequireAuth/RequireRole guards, createQueryClient, unwrap/ApiError, useZodForm/applyEnvelopeToForm
  - app deps (one instance each, per the matrix): react, react-dom, next, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers, @headlessui/react, tailwindcss + @tailwindcss/postcss — IDENTICAL versions to templates/frontend/nextjs (the `web` app); no new deps in this shell
  - env: NEXT_PUBLIC_API_BASE_URL (PUBLIC — empty in dev; a URL, never a secret)
  - a cookie-mode auth backend exposing `/auth/*` + the `admin`-role-gated `GET /admin/ping` — same-origin dev rewrites (next.config.ts), edge-routed or credentialed-CORS in prod (references/wiring/auth-end-to-end.md)
  - the backend's `admin` role/claim on the principal — this whole app is gated on it
exposes:
  - app: apps/admin — a SECOND, standalone Next.js (App Router) app: `.next/standalone` server output (Dockerfile, port 3001) + client-rendered whole-app-admin-gated routes. Its own deployable (own subdomain, own container service), never bundled into apps/web.
  - its co-located doc fragment: docs/fragment.md
-->

# Next.js (App Router) admin app (`apps/admin`)

The Stage 13a **foundation** for a drop-in admin tool: a SECOND, standalone
Next.js (App Router) app cloned from `templates/frontend/nextjs/` (the `web`
app), gated **whole-app** on the backend's `admin` role rather than on one
route. It reuses `@repo/api-client` + `@repo/web-shared` exactly like `apps/web`
— same provider wiring, same cookie-mode auth, same design tokens — with the
gate widened to cover every authenticated screen and the screens themselves
swapped for an admin shell (sidebar nav + stub feature pages) instead of a
public landing page. Lives at `templates/frontend/nextjs-admin/` in this
repo; scaffolding materializes it into `<project>/apps/admin/`, a workspace
member alongside `apps/web` and `packages/*` — **not** mutually exclusive
with `apps/web` (a project can run both: the public/user-facing app and the
internal admin tool are two different deployables for two different
audiences). Everything here is **subordinate to a project's existing
conventions** — when a scaffolded project has diverged, the project wins.

**What Stage 13a shipped:** the shell, nav, auth, and one working
admin-gated call (`GET /admin/ping`) end to end — proof the whole-app gate
and the shared client wiring actually work against a real backend, with
`users`, `moderation`, and `blog` as placeholder pages that resolved their
nav links and proved the route tree builds. **What Stage 13b added:** real
user-management UI at `app/(app)/users` — list/search/paginate via
`GET /admin/users` and per-user suspend/ban/reinstate/force-verify/edit-roles
/delete actions, driving the merged 13b backend endpoints through
`@repo/api-client`. `moderation` and `blog` remain placeholder pages; their
real content lands in later stages (13c/13d).

## Contents
- Composition contract
- Whole-app admin gate
- What it is / isn't
- Provider wiring
- Routing + screens
- The dev cross-origin cookie fix
- Styling
- Standalone deployable posture
- Build & deploy
- Testing
- Materialized-location paths
- For later stages (13c/13d)

## Composition contract

**NEEDS**
- **`@repo/api-client`** (`workspace:*`) — the generated hooks, models, and `configureApiClient`, called once in `app/providers.tsx`. Same package, same generated surface as `apps/web` — no separate admin-only client.
- **`@repo/web-shared`** (`workspace:*`) — `AuthProvider`, `RequireAuth`/`RequireRole` guards, `createQueryClient`, `getAccessToken`, `unwrap`/`ApiError`, `useZodForm`/`applyEnvelopeToForm`. Identical import surface to `apps/web`.
- **App dependencies** — `react`, `react-dom`, `next`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `tailwindcss` + `@tailwindcss/postcss`. Same versions as `apps/web`, pinned via `references/compatibility-matrix.md`. **No TipTap dependency in this shell** — the matrix pins the TipTap version line now (see the "Editor (WYSIWYG)" section) so it's ratified ahead of need, but `package.json` here doesn't install it until the Stage 13d editor work actually consumes it (no unused dep shipped in the foundation).
- **`NEXT_PUBLIC_API_BASE_URL`** — the PUBLIC backend origin (empty in dev; see the cookie fix below). A URL, never a secret.
- **A cookie-mode auth backend** exposing `/auth/*` (login/me/refresh/logout) and the `admin`-role-gated `GET /admin/ping` — the only admin backend surface that exists as of this stage. Reached same-origin (dev rewrites / prod edge routing) or via credentialed CORS.
- **The backend's `admin` role** on the authenticated principal — this app has no "authenticated but not admin" screen; see "Whole-app admin gate" below.

**EXPOSES**
- **`apps/admin`** — the Next.js app: `next build` → `.next/standalone` (the minimal traced server, what the Dockerfile ships, port **3001**) + `.next/static`. Every route (`app/(app)/*`) is admin-gated; there is no public route (`/` redirects straight to `/dashboard`, itself gated). It is an app, not an importable package.
- **Its co-located doc fragment** — `docs/fragment.md`, aggregated into the project root README by `just docs-generate`. Unique block id `frontend/nextjs-admin` — does not collide with `apps/web`'s `frontend/nextjs`.

## Whole-app admin gate

The defining delta from `templates/frontend/nextjs/`: there, `AdminGate`
wraps only the `/admin` route inside an otherwise generally-authenticated
app. Here, `app/(app)/layout.tsx` wraps `{children}` in
`<ProtectedGate><AdminGate>…</AdminGate></ProtectedGate>` — so **every**
route under `app/(app)/` (dashboard, users, moderation, blog, and anything a
later stage adds) requires both a valid session AND the decoded `admin` role
claim before it renders. There is no intermediate "signed in, not admin"
screen in this app, by design — an admin tool has nothing for a non-admin to
see. `AdminGate`'s fallback still redirects to `/dashboard` (ported from the
`web` app's `AdminGate` unchanged), but since `/dashboard` is itself inside
the gated tree, a non-admin who somehow authenticates just gets redirected
back to the same gated page — a harmless no-op navigation, not an error loop
— and never sees any content. That's intentional: they're locked out at the
UI, and the backend's 403 on `/admin/ping` (or any future admin endpoint)
remains the actual, authoritative gate regardless of what this client-side
check shows.

## What it is / isn't
- **Is:** the app shell — provider wiring, the whole-app-gated `app/` route
  tree, the admin nav chrome, and one proven admin-gated call.
- **Isn't:** a home for portable auth/query/forms logic (still
  `@repo/web-shared`, unchanged) or API-calling code (still
  `@repo/api-client`'s mutator, unchanged). Moderation and blog editing
  aren't built yet — those stay stub pages until 13c/13d land. User
  management shipped in Stage 13b (see "Routing + screens" below).

## Provider wiring
Byte-for-byte the same as `templates/frontend/nextjs/app/providers.tsx`:
`app/layout.tsx` is a server component rendering `<html>/<body>` +
`<Providers>`; `app/providers.tsx` (`"use client"`) calls
`configureApiClient({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "", cookieMode: true, getAccessToken })`
once at module scope, then mounts a per-mount `QueryClient` +
`AuthProvider` (`onAuthExpired` pushes to `/login`).

## Routing + screens
- `app/page.tsx` — a server component that calls `redirect("/dashboard")`
  (from `next/navigation`). An admin tool has no public landing page; this
  route exists only to send every visitor into the gated tree, which then
  decides (via `ProtectedGate`/`AdminGate`) whether they see anything.
- `app/(auth)/login` — the only public/auth screen. Unlike `apps/web`, there
  is **no** `register`/`verify-email`/`forgot-password`/`reset-password` —
  admins are seeded (by a backend script/migration, not built in this
  stage), not self-signup. Same anti-enumeration generic-401 message as the
  `web` app's login screen. On success, redirects to `/dashboard`.
- `app/(app)/layout.tsx` — the whole-app gate (see above) + the admin shell
  chrome: a sidebar with links to Dashboard/Users/Moderation/Blog, the
  current admin principal's email, and a logout button.
- `app/(app)/dashboard` — the landing screen once gated through: greets the
  principal and fires the **admin-gated `GET /admin/ping` acceptance call**
  (see below), rendering both the 200 success and the 403 branch.
- `app/(app)/users` — real user-management UI (Stage 13b): a searchable,
  paginated table (`GET /admin/users`, `?q=`/`?status=`/`?page=`/`?size=`)
  with per-row confirm-gated actions (Suspend/Ban/Reinstate/Force-verify/
  Delete via `components/users/ConfirmActionDialog.tsx`) and a roles editor
  (`components/users/RolesDialog.tsx`, `PUT .../roles`). Every mutation
  invalidates the list query (`getListAdminUsersAdminUsersGetQueryKey`) so
  the table reflects the new state; a 409 (invalid transition, or the
  backend's self-protection against an admin locking themselves out)
  surfaces the server's own message in the dialog rather than crashing or
  silently no-op'ing — see `components/users/actionMeta.ts`'s
  `describeApiError`.
- `app/(app)/moderation`, `app/(app)/blog` — stub pages
  (`components/ComingSoon.tsx`) that resolve the nav links and prove the
  route tree builds. Admin-gated purely by inheriting the layout — no gate
  logic of their own. Real content lands in 13c (moderation)/13d (blog,
  TipTap-based editor).

**The `/admin/ping` acceptance call.** `app/(app)/dashboard/page.tsx` fires a
live `useQuery` against the generated `adminPingAdminPingGet` hook and
renders both branches explicitly: the 200 success (the ping payload) and the
403 (`isApiError(error) && error.status === 403`) as a distinct "you don't
have admin access" banner. This is deliberate, not incidental — it's the
proof that this app's cookie-mode auth + whole-app client gate actually
reach a real admin-only backend endpoint and get a real answer, the same
"render both branches" discipline the `web` app's `/admin` screen uses.

## The dev cross-origin cookie fix
Identical mechanism to `templates/frontend/nextjs/`: `next.config.ts`'s
`async rewrites()` forwards `/auth`, `/admin`, `/items`, `/health`, `/readyz`
to `NEXT_DEV_API_PROXY ?? "http://localhost:8000"` so the browser only talks
to one origin locally (this app's own dev origin, `http://localhost:3001`),
letting the backend's `SameSite=Lax` cookie attach without `Secure` on
localhost. Pair with `NEXT_PUBLIC_API_BASE_URL=""` in `.env.local`.

## Styling
Same Tailwind v4 + token setup as `templates/frontend/nextjs/`:
`app/globals.css` (`@import "tailwindcss"`) wired through
`@tailwindcss/postcss`, `app/theme.css` the `@theme` token seam — cloned
verbatim, byte-for-byte the same tokens as `apps/web` (and the Vite SPA), so
the two apps share one visual language out of the box.

## Standalone deployable posture
This app is its **own** deployable: own subdomain (e.g.
`admin.example.com`), own container service, own port (**3001**, vs.
`apps/web`'s 3000 — chosen so both can run locally side by side with no
collision). It is never bundled into, or served from, the public `apps/web`
app — no admin code, no admin route, ships in that app's JS bundle. See
`docs/fragment.md`'s Deployment section for the infra-coordination note.

## Build & deploy
`next build` → `.next/standalone` + `.next/static`, same mechanism as
`apps/web`. The `Dockerfile` is a clone of `templates/frontend/nextjs/Dockerfile`
with every `apps/web` → `apps/admin`, `--filter "web..."` → `--filter "admin..."`,
and the runtime `PORT`/`EXPOSE` bumped to **3001**. Build from the project
root (context must see the whole workspace):
`docker build -f apps/admin/Dockerfile -t admin .`. Multi-stage, standalone
output, non-root `USER node`, pinned `node:24-bookworm-slim` base, only
`NEXT_PUBLIC_API_BASE_URL` as a build arg — no secret baked in.

## Testing
`pnpm --filter admin test` runs `vitest run` (jsdom + Testing Library + MSW,
same toolchain as `apps/web`, config in `vitest.config.ts`). Includes the
load-bearing **"login end-to-end via the shared client"** integration test
(`src/test/login-e2e.test.tsx`), adapted from the `web` app's version: it
renders the real `AuthProvider` + real `LoginPage` wired to the REAL
`@repo/api-client` hooks, MSW stubs `POST /auth/login` (roles-JWT response),
`GET /auth/me`, and `GET /admin/ping`, and asserts cookie mode, the
in-memory-only access token, `router.replace("/dashboard")` on success, and
`Authorization: Bearer` on both the `/auth/me` call and the dashboard's
`/admin/ping` call (`next/navigation` mocked, same two-screen test-harness
pattern the `web` app's test uses — here the second screen is
`DashboardPage` itself, since this app merges the `web` app's separate
`/admin` screen into the dashboard). There is no public-landing component
test here (unlike `apps/web`'s `app/page.test.tsx`) — `app/page.tsx` is a
pure server-side `redirect()`, not a renderable screen a Testing-Library
test can mount without triggering Next's redirect control-flow signal.

`src/test/users.test.tsx` (Stage 13b) covers the users screen the same way:
MSW-stubbed `GET /admin/users` renders a real page of users, a real
`POST .../suspend` confirm-and-go action fires the exact request and
refetches the list (proven by the row's status actually changing after the
stubbed refetch, not just the dialog closing), and a stubbed 409 conflict
response surfaces the server's own message in the dialog without crashing
and without triggering a refetch.

## Materialized-location paths
Same convention as `templates/frontend/nextjs/`: `tsconfig.json`'s `extends`
and `eslint.config.mjs`'s import of the root config are written as
`../../<file>` — correct for the materialized location (`<project>/apps/admin/`,
two levels below the project root). Don't "fix" them to be
firm-plugins-relative.

## For later stages (13c/13d)
- **Nav link targets / stub routes** Stage 13a created: `/dashboard`,
  `/users`, `/moderation`, `/blog` — all under `app/(app)/`, all admin-gated
  by inheriting `app/(app)/layout.tsx`. `/users` got its real UI in Stage
  13b (see "Routing + screens" above); `/moderation` and `/blog` are still
  stubs. A later stage replaces a stub page's body with real UI; it does not
  need to touch the gate, nav, or layout.
- **App identity**: package name `admin`, materializes to `apps/admin`, dev
  port **3001** (`next dev -p 3001` in `package.json`) and production port
  **3001** — both pinned off `apps/web`'s 3000 so `just dev` can run the
  public app and the admin app side by side with no collision.
- **Client wiring**: `app/providers.tsx` configures `@repo/api-client` once
  at module scope in cookie mode; any new feature page just imports the
  already-configured generated hooks — no new `configureApiClient` call
  needed anywhere else in this app.
- **TipTap**: pinned on the compatibility matrix now (`@tiptap/react`,
  `@tiptap/pm`, `@tiptap/starter-kit`, `@tiptap/extension-link`, all
  `3.28.x`), not yet installed. 13d adds it to this app's `package.json` when
  it builds the blog editor.
