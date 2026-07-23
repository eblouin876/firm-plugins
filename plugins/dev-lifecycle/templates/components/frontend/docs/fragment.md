<!-- fragment: block:components/frontend -->

## Setup
`@repo/web-shared` is the shared web layer over `@repo/api-client` (cookie-mode
`AuthProvider` + route guards, a `QueryClient` factory, error/JWT/form helpers).
A consuming app wires it once at startup:

1. `configureApiClient({ baseUrl, cookieMode: true, getAccessToken })` — import
   `getAccessToken` from `@repo/web-shared` so the in-memory access token rides
   every request. Source `baseUrl` from your framework's env var
   (`VITE_API_BASE_URL` / `NEXT_PUBLIC_API_BASE_URL`).
2. Mount `<QueryClientProvider client={createQueryClient()}><AuthProvider
   onAuthExpired={/* redirect to login */}>…</AuthProvider></QueryClientProvider>`
   — `AuthProvider` must sit inside the `QueryClientProvider`.
3. Gate protected UI with `<RequireAuth>` / `<RequireRole role="admin">`, passing
   your router's redirect as the `fallback` (the guards never navigate).
4. Wrap generated calls in `unwrap(...)` inside your `queryFn`/`mutationFn` so a
   401 surfaces as an error and drives the refresh flow.

Requires a cookie-mode auth backend (`/auth/*` + a role-gated route) with
credentialed CORS naming the web origin — see
`references/wiring/auth-end-to-end.md`.

## Maintenance
`react`, `@tanstack/react-query`, `react-hook-form`, `zod`, and
`@hookform/resolvers` are peer dependencies pinned via
`references/compatibility-matrix.md` (Frontend/web + Frontend testing rows), not
bumped independently. Run `pnpm --filter @repo/web-shared test` (vitest + jsdom +
MSW) after changing the auth/query/forms logic; the suite covers the cookie-mode
login/refresh/rotation/expiry lifecycle. When the backend's OpenAPI schema
changes, re-run `just client-generate` first so the generated hooks this package
imports stay current.
