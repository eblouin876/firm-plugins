"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";

// (1) Configure the shared api-client ONCE, before any generated hook fires.
// Deliberately at MODULE SCOPE (not inside the component body) — a module is
// evaluated exactly once per server process / browser load, so this is the
// guard against re-running on every render or remount (the SPA gets the same
// "once" property for free from main.tsx being the app's entrypoint, run
// once; this file is a component module instead, so the module-scope
// placement is what does that job here). SSR-safe: this only stores config,
// never reads `document`/`window` itself. On the server, `getAccessToken()`
// (from @repo/web-shared, browser-in-memory state) simply returns null — no
// Authorization header gets injected server-side, exactly as intended, since
// there's no per-request identity to attach here (Server Components make
// their own authenticated calls, if any, outside this client provider tree).
//   - baseUrl: the PUBLIC backend origin. Empty in dev (same-origin relative
//     URLs through next.config.ts's dev rewrites — see that file); set in
//     prod only for a cross-origin credentialed-CORS backend (see
//     .env.example).
//   - cookieMode: true — the web posture. The refresh token lives in an
//     HttpOnly cookie the JS never reads; only the short-lived access token
//     is in memory. Turns on `credentials: "include"`, the `X-Auth-Mode:
//     cookie` login header, and the CSRF double-submit echo (see
//     @repo/api-client's mutator.ts).
//   - getAccessToken: web-shared's in-memory access-token getter, so the
//     token rides every generated call as `Authorization: Bearer` without
//     any call site threading it by hand.
configureApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
  cookieMode: true,
  getAccessToken,
});

/**
 * Client-side provider tree, mounted once by the root layout
 * (`app/layout.tsx`, a server component) around `{children}`. Mirrors the
 * Vite SPA's `src/main.tsx` semantics — see that file — minus the router
 * provider (App Router owns routing itself; there's no `<RouterProvider>`
 * to mount).
 */
export const Providers = ({ children }: { children: ReactNode }): ReactNode => {
  const router = useRouter();

  // (2) One QueryClient per mount, created lazily via `useState(() => ...)`
  // rather than at module scope like `configureApiClient` above. This is
  // deliberately BROWSER-ONLY: a module-scope QueryClient would be shared
  // across every concurrent request on the Node server (leaking one user's
  // cached query data into another's response) and would double-register
  // AuthProvider's expiry listener on Fast Refresh / remount. `useState`'s
  // lazy initializer runs once per component instance, matching the SPA's
  // "one QueryClient for the app's lifetime" intent without the
  // cross-request leak SSR introduces.
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      {/* AuthProvider MUST mount INSIDE QueryClientProvider (it uses the
          generated React Query hooks). On unrecoverable expiry, redirect to
          /login imperatively via the App Router's client navigation hook —
          the direct analog of the SPA's `router.navigate("/login")`. */}
      <AuthProvider onAuthExpired={() => router.push("/login")}>{children}</AuthProvider>
    </QueryClientProvider>
  );
};
