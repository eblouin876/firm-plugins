import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { configureApiClient } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import { router } from "./router";
import "./styles/index.css";

// (1) Configure the shared api-client ONCE, before any generated hook fires.
//   - baseUrl: the PUBLIC backend origin. Empty in dev (same-origin relative
//     URLs through the Vite proxy — see vite.config.ts); set in prod only for a
//     cross-origin credentialed-CORS backend (see .env.example).
//   - cookieMode: true — the web posture. The refresh token lives in an
//     HttpOnly cookie the JS never reads; only the short-lived access token is
//     in memory. Turns on `credentials: "include"`, the `X-Auth-Mode: cookie`
//     login header, and the CSRF double-submit echo (see the api-client README).
//   - getAccessToken: web-shared's in-memory access-token getter, so the token
//     rides every generated call as `Authorization: Bearer` without any call
//     site threading it by hand.
configureApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  cookieMode: true,
  getAccessToken,
});

// (2) One QueryClient with the kit's auth-aware defaults (no retry on 401/403;
//   a 401 drives the single-flight refresh). AuthProvider MUST mount INSIDE the
//   QueryClientProvider (it uses the generated React Query hooks); RouterProvider
//   mounts inside AuthProvider so every route can `useAuth()` and the guards can
//   read auth state. On unrecoverable expiry, redirect to login imperatively via
//   the router instance.
const queryClient = createQueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error('Root element "#root" not found in index.html.');

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider onAuthExpired={() => void router.navigate("/login")}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
