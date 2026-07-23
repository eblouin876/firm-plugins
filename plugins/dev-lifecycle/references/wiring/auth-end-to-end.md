<!--
wiring: auth-end-to-end
covers: auth component (backend) <-> React web (cookie mode) <-> Expo mobile (bearer mode)
last-verified: 2026-07-23
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
sources:
  - https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
  - https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
  - https://docs.expo.dev/versions/latest/sdk/securestore/
  - references/security/secure-baseline.md
  - references/compatibility-matrix.md
-->

# Auth, end to end

**How one auth backend serves two very different clients** — a React web SPA and an Expo mobile app — over the *same* HTTP contract, with each client using the token-storage and CSRF posture that's correct for *its* runtime. This is a wiring reference: it stitches together pieces that each have their own canon doc, and is **subordinate to the project's existing conventions** — when they conflict, the project wins.

The three pieces:
- **Backend** — the `templates/components/security/auth/` component, vendored into either the FastAPI block (`templates/backend/fastapi`) or the Django block (`templates/backend/django`). One `AuthService` contract; two framework adapters (`fastapi.py`, `django.py`) that behave identically on the wire.
- **Web** — a React SPA importing `@repo/api-client` (`templates/packages/api-client`) in **cookie mode**.
- **Mobile** — an Expo app importing the same `@repo/api-client` in **bearer mode** (the default).

## Contents
- The one thing to understand first
- The two client modes (and why)
- Login → refresh → logout, in each mode
- Where CSRF applies (and where it can't help)
- RBAC: roles claim → gate → 403
- CORS is part of cookie mode
- Wiring checklist
- Related canon

## The one thing to understand first
There is **one** backend auth contract. The *client* picks its mode; the backend serves whichever the request asks for, per request:

- **Login selects the mode.** `POST /auth/login` reads the `X-Auth-Mode` request header. `X-Auth-Mode: cookie` → cookie mode; absent or any other value → **bearer** (the default). The mode is *never* inferred from `User-Agent` or any other signal.
- **Refresh and logout are dual-source.** `POST /auth/refresh` and `POST /auth/logout` decide per request by whether the `HttpOnly` `refresh_token` cookie is actually present on *this* request — not by any header the client declares. A forged or absent cookie cannot claim cookie mode; a genuine cookie-bearing browser request cannot accidentally fall onto the bearer path.

Everything below is a consequence of those two rules.

## The two client modes (and why)
The access token is short-lived and goes in the `Authorization: Bearer <access>` header in **both** modes. The modes differ only in **where the refresh token lives** — and that single choice drives everything else (CSRF, CORS, `credentials`).

### Web → cookie mode
| Concern | Web (cookie mode) |
| --- | --- |
| Access token | In memory (a JS variable / React state) — never persisted. |
| Refresh token | In an **`HttpOnly; Secure; SameSite=Lax; Path=/auth`** cookie the backend sets. JS **cannot read it.** |
| Login | `configureApiClient({ baseUrl, cookieMode: true })` → client sends `X-Auth-Mode: cookie`. Body returns `refresh_token: ""`; the real JWT is in the cookie. |
| Requests | `credentials: "include"` so the browser attaches the cookies. |
| CSRF | Double-submit: client echoes the non-HttpOnly `csrf_token` cookie as the `X-CSRF-Token` header on `/auth/refresh` + `/auth/logout`. |

**Why:** a browser has no secure secret store the app controls. The dangerous class is **XSS** — any injected script can read `localStorage`, `sessionStorage`, and any in-JS variable. Keeping the *refresh* token in an `HttpOnly` cookie puts it fully out of JS's reach, so an XSS payload can (at worst) ride the current short-lived access token but **cannot exfiltrate the long-lived refresh token** to mint tokens indefinitely off-site. The access token stays in memory (not `localStorage`) so it dies with the tab and isn't the persistent XSS prize either.

### Mobile → bearer mode (the default)
| Concern | Mobile (bearer mode) |
| --- | --- |
| Access token | In memory. |
| Refresh token | In **Expo SecureStore** (iOS Keychain / Android Keystore) — a real OS-backed secret store. |
| Login | Default config (`cookieMode` off / omitted) — no `X-Auth-Mode` header. Body returns the real `refresh_token`; app stores it in SecureStore. |
| Requests | `Authorization: Bearer <access>`; no cookies, no `credentials`. |
| CSRF | **None** — not needed (see below). |

**Why:** a native app has a real OS-backed secret store (Keychain/Keystore) and, crucially, **no ambient-cookie problem** — there is no browser to auto-attach credentials to a forged cross-site request, so CSRF simply doesn't exist as a class here. Cookies would only add friction (native HTTP clients handle them poorly) for zero security gain. Bearer + SecureStore is both simpler and correct for this runtime.

**The tradeoff in one line:** cookie mode trades "JS can't touch the refresh token" (great against XSS) for "the browser attaches it automatically" (which *creates* CSRF, handled by double-submit); bearer mode has neither property and needs neither defense.

## Login → refresh → logout, in each mode
The lifecycle is the same three calls; only the token transport differs. Refresh is **single-use with rotation and reuse detection** in both modes — every refresh mints a *new* refresh token and invalidates the old one; presenting an already-rotated refresh token revokes the whole token family (401). That reuse-detection is in the auth component's `AuthService.refresh`; it is mode-independent.

### Cookie mode (web)
1. **Login** — `POST /auth/login` with `X-Auth-Mode: cookie`. Backend sets two cookies: `refresh_token` (`HttpOnly`, `Path=/auth`) and `csrf_token` (non-HttpOnly, so JS can read it to echo it). Response body carries the access token and `refresh_token: ""`. App holds the access token in memory.
2. **Refresh** — `POST /auth/refresh` with `credentials: "include"` (browser sends the refresh cookie) **and** `X-CSRF-Token` = the `csrf_token` cookie's value. Backend enforces CSRF **first**, then rotates: mints a new refresh token, sets **both** cookies fresh (new refresh JWT + a new `csrf_token`), and returns a new access token (body `refresh_token` still `""`). The request body's `refresh_token` field is required by the schema but its value is ignored — the cookie is what's rotated.
3. **Logout** — `POST /auth/logout`, again with `credentials: "include"` + `X-CSRF-Token`. CSRF is enforced (logout is state-changing — it revokes the token family), then both cookies are cleared. Idempotent for the token itself once past the CSRF gate: a stale/expired cookie value still 204s.

### Bearer mode (mobile)
1. **Login** — `POST /auth/login`, no `X-Auth-Mode`. Body returns access + real `refresh_token`; app writes the refresh token to SecureStore, keeps access in memory.
2. **Refresh** — `POST /auth/refresh` with the refresh token in the request **body**. No cookie, no CSRF. Body returns the new access + new refresh token; app overwrites SecureStore with the rotated refresh token.
3. **Logout** — `POST /auth/logout` with the refresh token in the body. No CSRF. App clears SecureStore.

## Where CSRF applies (and where it can't help)
CSRF protection is enforced **only on the cookie path** of `/auth/refresh` and `/auth/logout`, and only *when the refresh cookie is present*. Nowhere else:

- **Login needs no CSRF** in either mode — it's authenticated by the credentials in the body (email + password), and there is no cookie yet for a forged request to ride.
- **Bearer mode needs no CSRF at all.** CSRF exploits the browser *automatically attaching ambient credentials* (cookies) to a cross-site request. A bearer token is attached *explicitly by the app's own code* in the `Authorization` header — an attacker's forged page cannot read it (it's not a cookie, and it's not exposed cross-origin) and the browser will not add it for them. No ambient credential ⇒ no CSRF.
- **Cookie mode needs CSRF because the cookie is ambient.** The double-submit check works because the forged cross-site request *can't read* the `csrf_token` cookie to copy it into the `X-CSRF-Token` header (same-origin policy blocks reading another origin's cookie), so it can't forge a matching pair. `SameSite=Lax` is a second, independent layer that blocks the cross-site request from carrying the cookie in the first place.

The double-submit transport itself lives in the auth component's framework-neutral `_cookies.py` (`generate_csrf_token`, `verify_double_submit`); the web client's echo half lives in `packages/api-client`'s `src/mutator.ts`.

## RBAC: roles claim → gate → 403
Authorization is orthogonal to the token transport — it works identically in both modes, because it reads the **access token**, which is a bearer `Authorization` header regardless of where the *refresh* token lives.

- The access JWT carries a **`roles`** claim (a list of role strings), minted by the auth component's `TokenService`.
- A protected route declares a role gate:
  - **FastAPI** — `dependencies=[Depends(require_admin)]` (built on the component's `require_roles`), which resolves the bearer principal and checks the role before the handler body runs.
  - **Django/DRF** — the component's `require_roles(request, auth_service, *roles)` / a `HasRole` permission.
- A caller with a valid token but the wrong role gets **`403`** (`permission_denied` → the `ErrorEnvelope` shape); a missing/invalid token gets **`401`**.
- **Worked example:** `GET /admin/ping` is gated on the `"admin"` role. It appears in the exported OpenAPI schema with `security: [{ HTTPBearer: [] }]` and documented `401`/`403` responses, so the generated `@repo/api-client` hook (`useAdminPingAdminPingGet`) exposes the typed error branches. This is the RBAC reference endpoint — copy its shape for any role-gated route.

## CORS is part of cookie mode
Cookie mode **requires** the backend's CORS to be configured for credentialed cross-origin requests, and this is a hard security constraint, not a convenience toggle:

- **Explicit origins only — never a `*` wildcard.** A wildcard `Access-Control-Allow-Origin` is *incompatible* with `credentials: "include"`: the browser refuses to send cookies to a wildcard origin. You must name the exact web origin(s), per environment (dev/staging/prod get distinct allowlists).
- **`Access-Control-Allow-Credentials: true`** must be set so the browser attaches and accepts cookies.
- Allow the `X-Auth-Mode` and `X-CSRF-Token` request headers.

Wire this through the `cors-lockdown` component (`templates/components/security/cors-lockdown/`), not by hand — it emits FastAPI `CORSMiddleware` / `django-cors-headers` settings from an explicit `CORSPolicy`. Bearer/mobile is same-origin-agnostic and doesn't need credentialed CORS, but a shared backend serving both should still scope CORS to the web origin.

## Wiring checklist
1. **Backend** — vendor the auth component into the FastAPI or Django block; construct `AuthService` with a real `JWT_SIGNING_KEY` and access/refresh TTLs at startup; expose `/auth/*` and at least one role-gated route (`/admin/ping`). Seed an admin user.
2. **Web** — `configureApiClient({ baseUrl, cookieMode: true })` once at startup; set CORS to the web origin with credentials enabled; keep the access token in memory only.
3. **Mobile** — `configureApiClient({ baseUrl })` (bearer, the default); store the refresh token in Expo SecureStore; never enable cookie mode on native.
4. Confirm refresh **rotation + reuse detection** works (a replayed refresh token 401s and revokes the family) and that a wrong-role token 403s.

For the step-by-step application of this in a scaffolded project, see the **`end-to-end-auth` recipe** (`references/recipes/end-to-end-auth.md`).

## Related canon
- `templates/components/security/auth/README.md` — the backend auth component (the `AuthService` contract, `_cookies.py` CSRF transport, `require_roles`).
- `templates/packages/api-client/README.md` — the client's "Cookie mode (web)" section (the mutator seam that implements the web half).
- `references/security/secure-baseline.md` — the firm security bar (Authentication & authorization, CORS lockdown, CSRF/cookie posture).
- `references/recipes/end-to-end-auth.md` — the recipe that applies this wiring.
- `references/compatibility-matrix.md` — the pinned versions (Expo SDK 57 / SecureStore, orval 8.22.x, React 19.x, PyJWT 2.13.x, argon2-cffi 25.1.x, Django 5.2 / DRF 3.17.x).
