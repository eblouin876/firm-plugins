import type { NextConfig } from "next";

// Next.js (App Router) config for the `web` app.
//
// DEV CROSS-ORIGIN COOKIE FIX (the load-bearing part — same rationale as the
// Vite SPA's vite.config.ts). Cookie-mode auth keeps the refresh token in an
// `HttpOnly; SameSite=Lax` cookie the backend sets. `SameSite=Lax` means the
// browser only attaches that cookie on SAME-SITE requests — so if this app
// (http://localhost:3000) called the backend (http://localhost:8000)
// cross-origin, the refresh cookie would never ride the request and the
// session couldn't refresh. The fix: rewrite every API path through Next's own
// dev server so the browser only ever talks to ONE origin. Pair this with
// `NEXT_PUBLIC_API_BASE_URL=""` in dev (see .env.example) so @repo/api-client
// issues same-origin RELATIVE URLs (`/auth/login`, not `http://localhost:8000/...`)
// that land on the rewrite rules below. On localhost the cookie needs no
// `Secure` flag; in production it does (see docs/fragment.md's Deployment
// section, once sub-agent D adds it, for the edge-routing / credentialed-CORS
// options — same two postures as the SPA).
const API_PROXY_TARGET = process.env.NEXT_DEV_API_PROXY ?? "http://localhost:8000";

// The backend path prefixes this app calls — identical list to the Vite SPA's
// vite.config.ts `API_PATHS`, kept in sync deliberately (same backend, same
// surfaces): the auth/admin/items surfaces plus the liveness/readiness probes.
const API_PATHS = ["/auth", "/admin", "/items", "/health", "/readyz"];

// Baseline security response headers on every route — the same three the
// Vite SPA's serve.mjs ships by default. A full CSP is deliberately left to
// the edge/CDN (it must be tuned to the app's own script/style/connect
// origins); these three are safe, app-agnostic hardening that ship by
// default regardless of hosting target.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  // Standalone server output (a minimal, self-contained `.next/standalone/`
  // tracing only the node_modules this app actually needs) — what the
  // Dockerfile's runtime stage ships, instead of the full workspace.
  output: "standalone",

  images: {
    // No remote image sources configured yet — a project that adds one
    // (an avatar CDN, a CMS) opts in here explicitly rather than allowing
    // arbitrary remote hosts by default.
    remotePatterns: [],
  },

  async rewrites() {
    // Two rules per path: the bare path itself (`/auth`) and everything under
    // it (`/auth/:rest*`) — Next's rewrite matcher needs an explicit `:rest*`
    // segment to catch sub-paths, unlike the Vite proxy's plain string-prefix
    // match.
    return API_PATHS.flatMap((path) => [
      { source: path, destination: `${API_PROXY_TARGET}${path}` },
      { source: `${path}/:rest*`, destination: `${API_PROXY_TARGET}${path}/:rest*` },
    ]);
  },

  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
