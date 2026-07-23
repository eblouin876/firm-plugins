<!-- fragment: block:frontend/nextjs -->

## Setup
`apps/web` is the Next.js (App Router) app — React 19 + Next 16 (Turbopack) +
TypeScript 6, Tailwind v4 via `@tailwindcss/postcss`, forms via
`@repo/web-shared`'s `useZodForm`. It talks to the backend through
`@repo/api-client` in **cookie mode**.

1. Install the workspace: `pnpm install` (from the project root).
2. Dev: run the backend (its `docker compose up`) and `just dev` — Next serves
   the app on `http://localhost:3000`. Leave `NEXT_PUBLIC_API_BASE_URL`
   **empty** (copy `apps/web/.env.example` to `apps/web/.env.local`):
   `next.config.ts`'s `async rewrites()` forwards `/auth`, `/admin`, `/items`,
   `/health`, `/readyz` to the compose backend (`http://localhost:8000`,
   override with `NEXT_DEV_API_PROXY`), so the browser talks to ONE origin.
   That same-origin path is what makes the backend's `SameSite=Lax` auth
   cookies work locally without `Secure` — a cross-origin `3000 -> 8000` setup
   would drop the refresh cookie.
3. `just build` runs `next build` (`.next/standalone` + `.next/static`);
   `just test` / `just lint` / `just typecheck` run the app's vitest + eslint
   + tsc via the workspace fan-out.

## Deployment
Unlike the Vite SPA (a static bundle any CDN can host), this app needs a
**Node runtime** in production — `next start` serves the `.next/standalone`
output the Dockerfile ships, because the dev rewrites/headers in
`next.config.ts` are server features with no static-hosting equivalent. That
makes `apps/web` a **container service** for infra purposes (Stage 9), not an
S3/CloudFront static upload: it needs a long-running process behind a load
balancer/target group, the same shape as the API block, not a bucket + CDN
distribution.

**SSR-auth posture, stated plainly:** this app does client-side auth for every
authenticated surface (the `(app)` route group — `AuthProvider` +
`RequireAuth`/`RequireRole` render-gates, identical posture to the SPA) and
server-side rendering only for the public, unauthenticated surface
(`app/page.tsx` — no auth check, no client-auth JS shipped to that route at
all). This app deliberately does **not** validate the session on the server
for authenticated routes (no middleware reading a cookie to gate `/dashboard`
server-side). Why: the backend's refresh-token cookie is scoped `Path=/auth`
(see `references/wiring/auth-end-to-end.md`) — the Next server process cannot
read it on a request to `/dashboard` (a different path), so there is no
session state available server-side to validate against without a broader,
separately-designed cookie-scoping and server-side-verification scheme.
Rather than fake a server check that can't actually see the session, the
authenticated route group stays client-rendered and gates in the browser, the
same as the SPA — the honest tradeoff of the Path-scoped-cookie design that
block already made. A project that wants real server-side session gating
needs to widen the cookie's `Path` and add middleware/route-handler
verification deliberately; that is out of scope for this block as shipped.

Two production postures for the cookie-mode API, both avoiding a
wildcard-CORS-with-credentials setup (which browsers reject):

- **Edge-routed API (simplest):** serve this app and route `/api/*` (or the
  API paths) to the backend from the SAME edge origin, keeping the browser
  same-origin. Leave `NEXT_PUBLIC_API_BASE_URL` empty.
- **Cross-origin API:** set `NEXT_PUBLIC_API_BASE_URL` to the API origin and
  configure the backend's CORS to name this app's exact origin with
  `Access-Control-Allow-Credentials: true` (never `*`), and set `Secure` on
  the auth cookies. Wire it through the `cors-lockdown` component.

Build the container from the project root (build context must see the whole
workspace — this app imports `@repo/api-client`/`@repo/web-shared`):
`docker build -f apps/web/Dockerfile -t web .`. The Dockerfile's runtime stage
runs `node apps/web/server.js` as the non-root `node` user, port 3000. Actual
provisioning (target group, health check, autoscaling) lands with the infra
block (Stage 9) treating this as a container service, not a static asset
upload.

## Maintenance
All versions follow `references/compatibility-matrix.md` (Frontend/web +
Frontend testing rows) — React 19, Next 16, Tailwind 4 (`@tailwindcss/postcss`
for this app, vs. the SPA's `@tailwindcss/vite`), Headless UI 2, RHF 7 / zod
4, and the testing toolchain — not bumped independently. When the backend's
OpenAPI schema changes, run `just client-generate` first so the generated
hooks this app imports stay current. Run `pnpm --filter web test` (vitest +
jsdom + MSW) after changing auth/routing/forms; the suite includes the
login-end-to-end-through-the-shared-client integration test (mocks
`next/navigation`, exercises the real `AuthProvider` + real generated hooks).
The design tokens in `app/theme.css` are a neutral placeholder the
`design-system` skill owns — components reference tokens (`bg-primary`,
`rounded-md`), never raw hex/px.

## Secrets
| `NEXT_PUBLIC_API_BASE_URL` (public, not a secret) | apps/web build | The backend's public API origin — a URL, not a credential; leave empty for same-origin edge routing/dev rewrites. Never put a token/key/password in a `NEXT_PUBLIC_`-prefixed var: it is inlined into the shipped browser bundle. |
