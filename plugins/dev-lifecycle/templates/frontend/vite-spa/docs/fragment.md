<!-- fragment: block:frontend/vite-spa -->

## Setup
`apps/web` is the React + Vite single-page app (react-router v7, Tailwind v4 +
Headless UI, forms via `@repo/web-shared`'s `useZodForm`). It talks to the
backend through `@repo/api-client` in **cookie mode**.

1. Install the workspace: `pnpm install` (from the project root).
2. Dev: run the backend (its `docker compose up`) and `just dev` — Vite serves
   the app on `http://localhost:5173`. Leave `VITE_API_BASE_URL` **empty** (copy
   `apps/web/.env.example` to `apps/web/.env.local`): the Vite dev server
   proxies `/auth`, `/admin`, `/items`, `/health`, `/readyz` to the compose
   backend (`http://localhost:8000`, override with `VITE_DEV_API_PROXY`), so the
   browser talks to ONE origin. That same-origin path is what makes the
   backend's `SameSite=Lax` auth cookies work locally without `Secure` — a
   cross-origin `5173 -> 8000` setup would drop the refresh cookie.
3. `just build` outputs the static bundle to `apps/web/dist/` (content-hashed
   assets + `index.html`); `just test` / `just lint` / `just typecheck` run the
   app's vitest + eslint + tsc via the workspace fan-out.

## Deployment
The build is a **static SPA** (`apps/web/dist/`) — host it on any static/CDN
target. Two production postures for the cookie-mode API, both avoiding a
wildcard-CORS-with-credentials setup (which browsers reject):

- **Edge-routed API (simplest):** serve the SPA and route `/api/*` (or the API
  paths) to the backend from the SAME edge origin (e.g. a CloudFront behavior),
  keeping the browser same-origin. Leave `VITE_API_BASE_URL` empty.
- **Cross-origin API:** set `VITE_API_BASE_URL` to the API origin and configure
  the backend's CORS to name this SPA's exact origin with
  `Access-Control-Allow-Credentials: true` (never `*`), and set `Secure` on the
  auth cookies. Wire it through the `cors-lockdown` component.

**SPA history fallback is required** wherever it's hosted: unknown paths must
return `/index.html` with 200 (on CloudFront, map 403/404 -> `/index.html`
200), so a deep link like `/admin` loads the app instead of a host 404. A
secondary **container** option ships too (`apps/web/Dockerfile` — multi-stage,
non-root, a zero-dependency static server that already does this fallback);
build it from the project root: `docker build -f apps/web/Dockerfile -t web .`.
Actual provisioning lands with the infra block (Stage 9).

## Maintenance
All versions follow `references/compatibility-matrix.md` (Frontend/web +
Frontend testing rows) — React 19, Vite 8, react-router 7, Tailwind 4, Headless
UI 2, RHF 7 / zod 4, and the testing toolchain — not bumped independently. When
the backend's OpenAPI schema changes, run `just client-generate` first so the
generated hooks this app imports stay current. Run `pnpm --filter web test`
(vitest + jsdom + MSW) after changing auth/routing/forms; the suite includes the
login-end-to-end-through-the-shared-client integration test. The design tokens
in `src/styles/theme.css` are a neutral placeholder the `design-system` skill
owns — components reference tokens (`bg-primary`, `rounded-md`), never raw
hex/px.

## Secrets
| `VITE_API_BASE_URL` (public, not a secret) | apps/web build | The backend's public API origin — a URL, not a credential; leave empty for same-origin edge routing. Never put a token/key/password in a `VITE_`-prefixed var: it is inlined into the shipped browser bundle. |
