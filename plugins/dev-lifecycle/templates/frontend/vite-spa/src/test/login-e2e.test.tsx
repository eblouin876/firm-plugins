import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { configureApiClient } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import { App } from "../App";
import { ProtectedRoute } from "../routes/ProtectedRoute";
import { AdminRoute } from "../routes/AdminRoute";
import { LoginPage } from "../routes/LoginPage";
import { DashboardPage } from "../routes/DashboardPage";
import { AdminPage } from "../routes/AdminPage";

// THE "login end-to-end via the shared client" integration test.
//
// It wires the REAL @repo/web-shared AuthProvider + the REAL @repo/api-client
// generated hooks (via the login screen and the admin screen) and intercepts
// the mutator's fetch at the network boundary with MSW — so it exercises the
// actual data path (login → X-Auth-Mode: cookie header → in-memory token →
// Bearer on every subsequent call), not a stubbed client. It proves:
//   1. logging in through the login screen lands on the authenticated dashboard
//      showing the /auth/me principal, and
//   2. a subsequent PROTECTED call (GET /admin/ping, fired by navigating into
//      the admin area) carries `Authorization: Bearer <access token>`.

const b64url = (obj: unknown): string => Buffer.from(JSON.stringify(obj)).toString("base64url");
const makeJwt = (payload: unknown): string =>
  `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.sig`;

// A JWT carrying the admin role, so the decoded (UX-only) roles claim lets the
// dashboard render the admin link and RequireRole render the admin screen.
const TOKEN = makeJwt({ sub: "user-1", roles: ["admin"], gen: 1 });
const ORIGIN = "http://localhost"; // jsdom's origin (see vite.config.ts test.environmentOptions)
const CSRF = "csrf-abc";

const server = setupServer();

// Per-test observations captured from the intercepted requests.
let loginAuthMode: string | null = null;
let meAuthHeader: string | null = null;
let adminAuthHeader: string | null = null;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

beforeEach(() => {
  loginAuthMode = null;
  meAuthHeader = null;
  adminAuthHeader = null;
  // The non-HttpOnly csrf_token cookie the backend would have set alongside the
  // HttpOnly refresh cookie; the mutator echoes it as X-CSRF-Token on
  // /auth/refresh + /auth/logout in cookie mode.
  document.cookie = `csrf_token=${CSRF}`;
  // Web posture: cookie mode + the in-memory access-token getter wired in — the
  // exact wiring apps/web/src/main.tsx does at startup.
  configureApiClient({ baseUrl: ORIGIN, cookieMode: true, getAccessToken });
  server.use(
    http.post(`${ORIGIN}/auth/login`, ({ request }) => {
      loginAuthMode = request.headers.get("X-Auth-Mode");
      // Cookie-mode login body: real access token, empty refresh_token (the real
      // refresh JWT would travel in the HttpOnly cookie).
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

const renderApp = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <App />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route
                path="admin"
                element={
                  <AdminRoute>
                    <AdminPage />
                  </AdminRoute>
                }
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("login end-to-end via the shared client", () => {
  it("logs in through the real api-client, renders the /auth/me principal, and a subsequent protected call carries the bearer", async () => {
    const user = userEvent.setup();
    renderApp();

    // Starts on the login screen.
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();

    // Type credentials and submit — drives web-shared's AuthProvider.login.
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // Lands on the authenticated dashboard showing the /auth/me principal.
    await screen.findByRole("heading", { name: "Dashboard" });
    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);

    // Login selected cookie mode; the access token is held in memory.
    expect(loginAuthMode).toBe("cookie");
    expect(getAccessToken()).toBe(TOKEN);
    // The /auth/me protected call carried the injected bearer token.
    expect(meAuthHeader).toBe(`Bearer ${TOKEN}`);

    // Navigate into the admin area → fires GET /admin/ping through the client.
    await user.click(screen.getByRole("link", { name: /open the admin area/i }));

    expect(await screen.findByText(/admin ping ok/i)).toBeInTheDocument();
    // The subsequent protected call carried the bearer token too.
    expect(adminAuthHeader).toBe(`Bearer ${TOKEN}`);
  });
});
