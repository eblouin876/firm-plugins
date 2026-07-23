/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Vite SPA config for the `web` app.
//
// DEV CROSS-ORIGIN COOKIE FIX (the load-bearing part). Cookie-mode auth keeps
// the refresh token in an `HttpOnly; SameSite=Lax` cookie the backend sets.
// `SameSite=Lax` means the browser only attaches that cookie on SAME-SITE
// requests — so if the SPA (http://localhost:5173) called the backend
// (http://localhost:8000) cross-origin, the refresh cookie would never ride the
// request and the session couldn't refresh. The fix: proxy every API path
// through the Vite dev server so the browser only ever talks to ONE origin
// (the dev server's), keeping requests same-origin. Pair this with
// `VITE_API_BASE_URL=""` in dev (see .env.example) so @repo/api-client issues
// same-origin RELATIVE URLs (`/auth/login`, not `http://localhost:8000/...`)
// that land on the proxy rules below. On localhost the cookie needs no
// `Secure` flag; in production it does (see docs/fragment.md's Deployment
// section for the CloudFront `/api/*` and credentialed-CORS options).
const API_PROXY_TARGET = process.env.VITE_DEV_API_PROXY ?? "http://localhost:8000";

// The backend path prefixes the SPA calls — the auth/admin/items surfaces plus
// the liveness/readiness probes. Kept in one list so the proxy and any future
// same-origin rewrite stay in sync.
const API_PATHS = ["/auth", "/admin", "/items", "/health", "/readyz"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((path) => [
        path,
        { target: API_PROXY_TARGET, changeOrigin: true },
      ]),
    ),
  },
  // Vitest config lives here so component tests share the app's real Vite
  // transform pipeline (the React plugin's JSX/Fast-Refresh handling). jsdom
  // gives `document`/`window`/`document.cookie` so React renders headlessly and
  // the api-client mutator's cookie-mode CSRF echo works; a fixed origin lets
  // MSW match absolute handler URLs. `css: false` skips CSS processing in tests
  // (no test imports the Tailwind entry, and it keeps the Oxide engine out of
  // the test path). See references/testing/frontend-testing.md.
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost" } },
    globals: true,
    css: false,
    setupFiles: ["./vitest.setup.ts"],
  },
});
