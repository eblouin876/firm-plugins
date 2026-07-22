<!-- fragment: block:packages/api-client -->

## Setup
Call `configureApiClient({ baseUrl })` once at app startup, before any
generated hook fires a request — this package never reads `process.env`
itself. Source `baseUrl` from your own framework's env var:

| Framework | Env var |
| --- | --- |
| Vite (web) | `VITE_API_BASE_URL` |
| Next.js (App Router) | `NEXT_PUBLIC_API_BASE_URL` |
| Expo (mobile) | `EXPO_PUBLIC_API_BASE_URL` |

Run `just client-generate` whenever the backend's OpenAPI schema has
changed since your last install, so the hooks/models you're building
against are current.

## Maintenance
Run `just client-generate` whenever the backend schema changes — it
regenerates `src/generated/` wholesale (orval, fetch mode); commit the
diff. `react` and `@tanstack/react-query` are matrix-governed: their pins
follow `references/compatibility-matrix.md`, not an independent bump.
