<!--
recipe: end-to-end-auth
applies-to:
  - backend block: fastapi OR django (one auth contract, either adapter)
  - frontend block: any React web block (cookie mode) — pairs with @repo/api-client
  - mobile block: any Expo block (bearer mode) — pairs with @repo/api-client
last-verified: 2026-07-23
provenance: manual
sources:
  - https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
  - https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
  - https://docs.expo.dev/versions/latest/sdk/securestore/
  - https://pyjwt.readthedocs.io/en/stable/
  - references/wiring/auth-end-to-end.md
  - references/security/secure-baseline.md
  - references/compatibility-matrix.md
-->

# End-to-end auth

Wire register/login/refresh/logout with role-based access control across a scaffolded monorepo: one backend auth contract serving a React web SPA (cookie mode) and an Expo mobile app (bearer mode) through the shared typed client. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Security checklist
- Doc fragment

## What this wires
Applying this recipe gives a project working authentication end to end: users can register, log in, refresh (single-use rotation with reuse detection), and log out; a `roles` claim on the access JWT gates protected routes with a `403` on the wrong role; and both a web SPA and a mobile app authenticate against the same backend, each with the token-storage/CSRF posture correct for its runtime.

It **composes existing pieces** — it invents no new infrastructure:
- **`templates/components/security/auth/`** — the framework-neutral auth core (`AuthService`: Argon2id hashing, PyJWT HS256 access/refresh tokens, rotation + reuse detection), its `_cookies.py` double-submit CSRF transport, and the `require_roles` RBAC gate. Vendored into the backend block.
- **A backend block** — `templates/backend/fastapi` or `templates/backend/django` — which hosts the vendored component, exposes `/auth/*` and the `/admin/ping` RBAC example, and owns the `UserStore`/`RefreshTokenStore` against the real DB.
- **`templates/components/security/cors-lockdown/`** — emits the credentialed CORS the web cookie mode requires.
- **`templates/packages/api-client/`** — the shared `@repo/api-client`; its `src/mutator.ts` cookie-mode seam supplies the web half (`X-Auth-Mode: cookie`, `credentials: "include"`, `X-CSRF-Token` echo). Bearer mode (default) is the mobile half.
- **A frontend block** (React web) and/or **a mobile block** (Expo) — the consumers that call `configureApiClient(...)` and hold the access token in memory.

The full conceptual model — the two modes and *why* — is `references/wiring/auth-end-to-end.md`; this recipe is the ordered how-to.

## Prerequisites
- A scaffolded monorepo (Stage 1) with a **backend block** (`templates/backend/fastapi` or `templates/backend/django`) and the **`@repo/api-client`** package present, plus at least one consumer block (a React web app, an Expo app, or both).
- The **auth component vendored** into the backend block (its files copied under `app/core/security/auth/` for FastAPI or `core/security/auth/` for Django, with the app-level `UserStore`/`RefreshTokenStore` implemented against the project's ORM/session — the backend block's Stage 5a/5b wiring is the reference).
- A **PostgreSQL** database (matrix: **18.x**) with the users/refresh-tokens tables migrated.
- Runtime dependencies per `references/compatibility-matrix.md`: **PyJWT 2.13.x** + **argon2-cffi 25.1.x** (backend); **orval 8.22.x** + **@tanstack/react-query 5.101.x** + **React 19.x** (web/client); **Expo SDK 57** / **expo-secure-store** (mobile); **Django 5.2 LTS** + **DRF 3.17.x** on the Django track; **django-cors-headers 4.9.x** for that track's CORS.

## Wire-up steps
1. **Compose the auth component into the backend block.** Confirm the vendored `AuthService` is constructed once at startup with a real signing key and TTLs, and that `/auth/register|login|refresh|logout|me` plus the `/admin/ping` RBAC example route are mounted. Don't re-author the component — the backend block's own README documents its store/exception wiring; follow it.

2. **Set the backend auth config (secrets never inlined).** Provide these as environment/secret values (names from the FastAPI block's `app/core/config.py`; the Django track mirrors them):
   - `JWT_SIGNING_KEY` — the HS256 secret. Generate a high-entropy random value (e.g. `openssl rand -hex 32`); load it from the environment/secret store, **never** commit it. The app resolves it via the secrets-loading component, and it never appears in a `Settings` repr.
   - `JWT_ACCESS_TTL_SECONDS` / `JWT_REFRESH_TTL_SECONDS` — short access TTL (minutes), longer refresh TTL (days); the refresh cookie's `max_age` is pinned to the refresh TTL so it never outlives its token.
   - `FRONTEND_BASE_URL` — the SPA origin that email-verification / password-reset links are built against (default `http://localhost:5173`; override per environment).
   - `SMTP_HOST` (+ `SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM`) — required in any real environment for verification/reset email delivery; unset falls open to a dev-only console sender that logs the raw token. **A real `SMTP_HOST` is a required deploy step, not a code change.**

3. **Choose the mode(s) and wire the client.**
   - **Web (cookie mode):** call `configureApiClient({ baseUrl, cookieMode: true })` once at app startup (before any generated hook fires). Keep the access token **in memory only** (never `localStorage`). The client then sends `X-Auth-Mode: cookie` on login, `credentials: "include"` on every request, and echoes the `csrf_token` cookie as `X-CSRF-Token` on refresh/logout — see `templates/packages/api-client/README.md`'s "Cookie mode (web)".
   - **Mobile (bearer mode — the default):** call `configureApiClient({ baseUrl })` with `cookieMode` omitted. Store the refresh token in **Expo SecureStore** (`expo-secure-store`), keep the access token in memory, and send it as `Authorization: Bearer`. **Never** enable cookie mode on native.

4. **Enable credentialed CORS for cookie mode (web only).** Set the backend's `AUTH_COOKIE_MODE_ENABLED=true` (secure default is `false`) and `CORS_ALLOWED_ORIGINS` to the **explicit** web origin(s) — never a `*` wildcard, which is incompatible with `credentials: "include"`. This flips the `cors-lockdown` policy to `allow_credentials=True` and adds `X-CSRF-Token`/`X-Auth-Mode` to allowed headers. A mobile-only or same-origin deployment leaves this off. Distinct allowlists per environment (dev/staging/prod).

5. **Seed an admin.** Roles are **never** settable over the wire — `POST /auth/register` has no `roles` field and always creates users with empty roles. Create the first admin server-side with the component's sanctioned `seed_admin(session, email, password)` path (a one-off script or a fixture; it commits immediately and is the only place `roles=["admin"]` is ever constructed). Verify with `GET /admin/ping`: an admin's token → `200`, a non-admin's → `403`, no/invalid token → `401`.

6. **Verify the security-critical behaviors.** Confirm refresh **rotation + reuse detection** (a replayed refresh token returns `401` and revokes the whole family), that the web refresh/logout calls are rejected `403` without a valid `X-CSRF-Token`, and that the refresh cookie is `HttpOnly; Secure; SameSite=Lax; Path=/auth`.

## Security checklist
- [ ] `JWT_SIGNING_KEY` is high-entropy, loaded from the environment/secret store, and never committed or logged.
- [ ] Access token lives in memory only (web and mobile); refresh token in an `HttpOnly` cookie (web) or SecureStore (mobile) — never in `localStorage`/`sessionStorage`.
- [ ] Cookie mode: refresh cookie is `HttpOnly; Secure; SameSite=Lax; Path=/auth`; CSRF double-submit enforced on `/auth/refresh` + `/auth/logout`.
- [ ] CORS names explicit origins with `allow_credentials=True` — no `*` wildcard; distinct allowlists per environment.
- [ ] Refresh rotation + reuse detection verified (replayed token → 401, family revoked).
- [ ] Admin role granted only via `seed_admin` server-side; `/auth/register` cannot self-grant roles; `/admin/ping` returns 403 on the wrong role.
- [ ] A real `SMTP_HOST` is configured in every non-dev environment (the console sender is dev-only and logs raw tokens).
- [ ] Auth endpoints (login, refresh, password reset) are rate-limited / lockout-guarded per `references/security/secure-baseline.md`.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Authentication (end to end)
- **Setup:** Users register/login/refresh/logout against the backend auth component; role-based access control gates protected routes (`GET /admin/ping` is the reference). Web uses **cookie mode** — access token in memory, refresh token in an `HttpOnly; Secure; SameSite=Lax; Path=/auth` cookie, CSRF double-submit on refresh/logout — enabled via `configureApiClient({ baseUrl, cookieMode: true })`. Mobile uses **bearer mode** (the default) — access token in memory, refresh token in Expo SecureStore, `Authorization: Bearer`, no CSRF. See `references/wiring/auth-end-to-end.md`.
- **Secrets:** `JWT_SIGNING_KEY` — HS256 signing secret, generate with `openssl rand -hex 32`, load from the environment/secret store (never commit). `SMTP_HOST` (+ `SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM`) — email relay for verification/reset links; required in every non-dev environment.
- **Config:** `JWT_ACCESS_TTL_SECONDS`/`JWT_REFRESH_TTL_SECONDS` (short access, longer refresh), `FRONTEND_BASE_URL` (SPA origin for email links). Cookie mode additionally needs `AUTH_COOKIE_MODE_ENABLED=true` and `CORS_ALLOWED_ORIGINS` set to explicit web origin(s) — never `*`.
- **Maintenance:** The first admin is created server-side with the auth component's `seed_admin(session, email, password)` (roles are never settable over the wire). Keep PyJWT / argon2-cffi and the client (orval / @tanstack/react-query) on the versions pinned in `references/compatibility-matrix.md`; regenerate `@repo/api-client` after any auth-route change.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 5d, #46). Composes existing
catalog components/blocks only — no new infrastructure. Every version-sensitive
step cites references/compatibility-matrix.md; every step defaults to the secure
option per references/security/secure-baseline.md.
-->
