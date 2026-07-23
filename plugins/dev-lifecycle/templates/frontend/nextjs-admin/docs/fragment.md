<!-- fragment: block:frontend/nextjs-admin -->

## Setup
`apps/admin` is a SECOND, standalone Next.js (App Router) app — React 19 +
Next 16 (Turbopack) + TypeScript 6, Tailwind v4 via `@tailwindcss/postcss` —
cloned from `apps/web`'s block with the admin gate widened to the **whole
app**. It talks to the backend through `@repo/api-client` in **cookie mode**,
same as `apps/web`.

1. Install the workspace: `pnpm install` (from the project root) — installs
   `apps/admin` alongside every other workspace member; no separate install
   step.
2. Dev: run the backend (its `docker compose up`) and `just dev` — Next
   serves this app on **port 3001** (`next dev -p 3001` in `package.json`),
   pinned off `apps/web`'s 3000 so both frontends run side by side under
   `just dev` with no collision. Leave
   `NEXT_PUBLIC_API_BASE_URL` **empty** (copy `apps/admin/.env.example` to
   `apps/admin/.env.local`): `next.config.ts`'s `async rewrites()` forwards
   `/auth`, `/admin`, `/items`, `/health`, `/readyz` to the compose backend
   (`http://localhost:8000`, override with `NEXT_DEV_API_PROXY`), so the
   browser talks to ONE origin — the same-origin path the backend's
   `SameSite=Lax` auth cookies need locally.
3. Sign in with a seeded admin account (this app has no self-signup — see
   Deployment/Maintenance below) and confirm the dashboard's admin-ping
   check reports success; that call is the proof this app's auth end-to-end
   wiring actually works.
4. `just build` runs `next build` (`.next/standalone` + `.next/static`);
   `just test` / `just lint` / `just typecheck` run this app's vitest +
   eslint + tsc via the workspace fan-out.

## Deployment
This app is a **separate deployable** from `apps/web` — its own container
service, its own subdomain (e.g. `admin.example.com`), never bundled into or
served from the public `apps/web` app: no admin code, no admin route, ships
in that app's JS bundle. Coordinate the actual subdomain/routing/TLS with
whichever infra stage provisions it (Stage 9's infra block treats this the
same way it treats `apps/web` — a long-running container behind a load
balancer/target group, not a static asset upload) — this block does not
provision that infrastructure itself, only the container image it runs.

Like `apps/web`, this needs a **Node runtime** in production (`next start`
serving the `.next/standalone` output) because the dev rewrites/headers in
`next.config.ts` are server features with no static-hosting equivalent.
Build the container from the project root (build context must see the whole
workspace — this app imports `@repo/api-client`/`@repo/web-shared`):
`docker build -f apps/admin/Dockerfile -t admin .`. The Dockerfile's runtime
stage runs `node apps/admin/server.js` as the non-root `node` user, **port
3001** (not `apps/web`'s 3000 — deliberately different so both containers
can run side by side, e.g. in `templates/monorepo/docker-compose.yml`'s
commented `admin` service, with no port collision).

Same two production CORS/cookie postures as `apps/web` (edge-routed API,
leaving `NEXT_PUBLIC_API_BASE_URL` empty; or a cross-origin API with
credentialed CORS naming this app's exact origin) — see that block's own
Deployment note for the full statement, unchanged here.

**Whole-app admin gate, stated plainly:** every route in this app requires
the backend's `admin` role claim to render at all (see the README's "Whole-
app admin gate" section) — there is no non-admin experience to design for.
The gate is UX only; the backend's 401/403 on every call is authoritative.

## Maintenance
All versions follow `references/compatibility-matrix.md` (Frontend/web +
Frontend testing rows, same pins as `apps/web` — not bumped independently
between the two apps) plus the "Editor (WYSIWYG)" TipTap rows once 13d
installs them. Admins are seeded (a backend admin-creation script or
migration, owned by a later stage — not built in this foundation stage),
never self-registered — there is no `/register` flow in this app to keep in
sync with the backend. When the backend's OpenAPI schema changes, run `just
client-generate` first so the generated hooks this app imports stay current.
Run `pnpm --filter admin test` (vitest + jsdom + MSW) after changing
auth/routing — the suite includes the login-end-to-end-through-the-shared-
client integration test (mocks `next/navigation`, exercises the real
`AuthProvider` + real generated hooks, asserts the bearer token rides the
dashboard's `/admin/ping` call). The design tokens in `app/theme.css` are
byte-for-byte the same neutral placeholder `apps/web` uses — the
`design-system` skill owns both together, not independently.

## Secrets
| `NEXT_PUBLIC_API_BASE_URL` (public, not a secret) | apps/admin build | The backend's public API origin — a URL, not a credential; leave empty for same-origin edge routing/dev rewrites. Never put a token/key/password in a `NEXT_PUBLIC_`-prefixed var: it is inlined into the shipped browser bundle. |
