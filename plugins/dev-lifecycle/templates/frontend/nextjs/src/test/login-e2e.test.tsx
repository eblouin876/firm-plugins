import { useState } from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import LoginPage from "../../app/(auth)/login/page";
import AdminPage from "../../app/(app)/admin/page";

// THE "login end-to-end via the shared client" integration test — the Next.js
// counterpart to the Vite SPA's `src/test/login-e2e.test.tsx`. Same intent,
// same MSW-at-the-network-boundary strategy, same real @repo/web-shared
// AuthProvider + real @repo/api-client generated hooks; the only structural
// difference is routing. The SPA drives real navigation through a
// MemoryRouter; the App Router has no analogous in-memory test harness (there
// is no `<RouterProvider>` to mount — routing is file-system-based and
// resolved by Next's own server/client runtime, not a library the test can
// instantiate standalone) — so `next/navigation` is mocked, and this file
// supplies its own minimal two-screen test harness whose active screen swaps
// in response to the MOCKED router's `replace()` call — the same
// login-drives-navigation behavior the real app exhibits, without needing a
// full Next App Router test runtime. It proves:
//   1. logging in through the real login screen calls the real api-client's
//      POST /auth/login in cookie mode, holds the access token in memory only,
//      and drives `router.replace("/dashboard")`, and
//   2. TWO subsequent protected calls — AuthProvider's own `GET /auth/me`
//      (fired automatically once a token exists) and, once the harness swaps
//      to the real admin screen, `GET /admin/ping` — both carry
//      `Authorization: Bearer <access token>`.

const b64url = (obj: unknown): string => Buffer.from(JSON.stringify(obj)).toString("base64url");
const makeJwt = (payload: unknown): string =>
  `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.sig`;

// A JWT carrying the admin role, so the decoded (UX-only) roles claim lets
// AdminGate (RequireRole "admin") render the real admin screen.
const TOKEN = makeJwt({ sub: "user-1", roles: ["admin"], gen: 1 });
const ORIGIN = "http://localhost"; // jsdom's origin (see vitest.config.ts environmentOptions)
const CSRF = "csrf-abc";

const server = setupServer();

// Per-test observations captured from the intercepted requests.
let loginAuthMode: string | null = null;
let meAuthHeader: string | null = null;
let adminAuthHeader: string | null = null;

// The mocked router. `replace`/`push` are spies AND drive the test harness's
// own screen state via `onNavigate` — see `Harness` below. Declared with
// `let`/`const` here but only ever READ inside closures that run during
// render/interaction (well after this module has finished initializing), so
// the temporal-dead-zone ordering between this and the hoisted `vi.mock`
// factory below is never actually observed.
const replaceSpy = vi.fn<(path: string) => void>(() => {});
const pushSpy = vi.fn<(path: string) => void>(() => {});
let onNavigate: ((path: string) => void) | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: (path: string) => {
      replaceSpy(path);
      onNavigate?.(path);
    },
    push: (path: string) => {
      pushSpy(path);
      onNavigate?.(path);
    },
  }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

beforeEach(() => {
  loginAuthMode = null;
  meAuthHeader = null;
  adminAuthHeader = null;
  replaceSpy.mockClear();
  pushSpy.mockClear();
  onNavigate = null;
  // The non-HttpOnly csrf_token cookie the backend would have set alongside
  // the HttpOnly refresh cookie; the mutator echoes it as X-CSRF-Token on
  // /auth/refresh + /auth/logout in cookie mode.
  document.cookie = `csrf_token=${CSRF}`;
  // Web posture: cookie mode + the in-memory access-token getter wired in —
  // the exact wiring app/providers.tsx does at startup.
  configureApiClient({ baseUrl: ORIGIN, cookieMode: true, getAccessToken });
  server.use(
    http.post(`${ORIGIN}/auth/login`, ({ request }) => {
      loginAuthMode = request.headers.get("X-Auth-Mode");
      // Cookie-mode login body: real access token, empty refresh_token (the
      // real refresh JWT would travel in the HttpOnly cookie).
      return HttpResponse.json(
        { access_token: TOKEN, refresh_token: "", token_type: "bearer" },
        { status: 200 },
      );
    }),
    http.get(`${ORIGIN}/auth/me`, ({ request }) => {
      meAuthHeader = request.headers.get("Authorization");
      return HttpResponse.json({ id: "user-1", email: "user@example.com" }, { status: 200 });
    }),
    http.get(`${ORIGIN}/admin/ping`, ({ request }) => {
      adminAuthHeader = request.headers.get("Authorization");
      return HttpResponse.json({ status: "ok" }, { status: 200 });
    }),
  );
});

afterEach(() => {
  server.resetHandlers();
  configureApiClient({ baseUrl: "" });
});

/**
 * Minimal test-only two-screen harness: renders the REAL `LoginPage` until
 * the mocked router's `replace("/dashboard")` fires (login success), then
 * swaps to the REAL `AdminPage` — standing in for the App Router actually
 * navigating from `/login` to `/dashboard`/`/admin`, which this test can't
 * literally do (no App Router test runtime). Both screens mount inside the
 * SAME `AuthProvider`/`QueryClientProvider`, so the access token set by login
 * carries straight through to the admin screen's protected call, exactly as
 * it would across a real client-side navigation.
 */
const Harness = () => {
  const [view, setView] = useState<"login" | "admin">("login");
  onNavigate = (path) => {
    if (path === "/dashboard") setView("admin");
  };
  return view === "login" ? <LoginPage /> : <AdminPage />;
};

const renderApp = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("login end-to-end via the shared client (Next.js)", () => {
  it("logs in through the real api-client, redirects to /dashboard, and carries the bearer on subsequent protected calls", async () => {
    const user = userEvent.setup();
    renderApp();

    // Starts on the login screen.
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();

    // Type credentials and submit — drives web-shared's AuthProvider.login.
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Login selected cookie mode; the access token is held in memory only
    // (never persisted), and login drives router.replace("/dashboard") — the
    // Next analog of the SPA's `useNavigate()` call.
    await waitFor(() => expect(loginAuthMode).toBe("cookie"));
    expect(getAccessToken()).toBe(TOKEN);
    expect(replaceSpy).toHaveBeenCalledWith("/dashboard");
    expect(pushSpy).not.toHaveBeenCalled();

    // AuthProvider's own /auth/me query (enabled once a token exists, fired
    // with no further user action) carried the injected bearer token.
    await waitFor(() => expect(meAuthHeader).toBe(`Bearer ${TOKEN}`));

    // The harness swapped to the real AdminPage on that redirect (AdminGate
    // renders it because the roles claim decoded from TOKEN includes
    // "admin"), and its GET /admin/ping call also carries the bearer.
    expect(await screen.findByText(/admin ping ok/i)).toBeInTheDocument();
    expect(adminAuthHeader).toBe(`Bearer ${TOKEN}`);
  });
});
