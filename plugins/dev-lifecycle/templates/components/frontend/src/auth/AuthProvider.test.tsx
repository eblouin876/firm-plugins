import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { adminPingAdminPingGet, configureApiClient } from "@repo/api-client";
import { createQueryClient } from "../query/createQueryClient";
import { unwrap } from "../errors/unwrap";
import { getAccessToken, __resetAuthBridge } from "./authBridge";
import { AuthProvider } from "./AuthProvider";
import { RequireRole } from "./guards";
import { useAuth } from "./useAuth";

// --- token helpers --------------------------------------------------------
const b64url = (obj: unknown): string => Buffer.from(JSON.stringify(obj)).toString("base64url");
const makeJwt = (payload: unknown): string =>
  `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.sig`;

// TOKEN_A is what login mints; TOKEN_B is the rotated token a refresh returns.
// Both carry the admin role so RequireRole renders in the happy path.
const TOKEN_A = makeJwt({ sub: "user-1", roles: ["admin"], gen: 1 });
const TOKEN_B = makeJwt({ sub: "user-1", roles: ["admin"], gen: 2 });

const ORIGIN = "http://localhost";
const CSRF = "csrf-xyz";

// --- MSW server -----------------------------------------------------------
const server = setupServer();

// Per-test observations.
let loginAuthMode: string | null = null;
let refreshCount = 0;
let refreshCsrfHeader: string | null = null;

const loginHandler = () =>
  http.post(`${ORIGIN}/auth/login`, ({ request }) => {
    loginAuthMode = request.headers.get("X-Auth-Mode");
    return HttpResponse.json(
      { access_token: TOKEN_A, refresh_token: "", token_type: "bearer" },
      { status: 200 },
    );
  });

const meHandler = () =>
  http.get(`${ORIGIN}/auth/me`, () =>
    HttpResponse.json({ id: "user-1", email: "user@example.com" }, { status: 200 }),
  );

const refreshOkHandler = () =>
  http.post(`${ORIGIN}/auth/refresh`, ({ request }) => {
    refreshCount += 1;
    refreshCsrfHeader = request.headers.get("X-CSRF-Token");
    return HttpResponse.json(
      { access_token: TOKEN_B, refresh_token: "", token_type: "bearer" },
      { status: 200 },
    );
  });

const unauthorized = () =>
  HttpResponse.json(
    { error: { code: "unauthenticated", message: "Not authenticated" } },
    { status: 401 },
  );

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

beforeEach(() => {
  loginAuthMode = null;
  refreshCount = 0;
  refreshCsrfHeader = null;
  __resetAuthBridge();
  // The non-HttpOnly csrf_token cookie the backend would have set; the mutator
  // echoes it as X-CSRF-Token on /auth/refresh + /auth/logout in cookie mode.
  document.cookie = `csrf_token=${CSRF}`;
  // Web posture: cookie mode + the in-memory access-token getter wired in.
  configureApiClient({ baseUrl: ORIGIN, cookieMode: true, getAccessToken });
});

afterEach(() => {
  server.resetHandlers();
  configureApiClient({ baseUrl: "" });
});

// --- harness --------------------------------------------------------------
const AdminPing = () => {
  const { isAuthenticated } = useAuth();
  const ping = useQuery({
    queryKey: ["admin-ping"],
    queryFn: async () => unwrap(await adminPingAdminPingGet()),
    enabled: isAuthenticated,
  });
  return <div data-testid="ping">{ping.isSuccess ? "ping-ok" : "ping-pending"}</div>;
};

const Harness = () => {
  const auth = useAuth();
  return (
    <div>
      <button onClick={() => void auth.login("user@example.com", "pw").catch(() => {})}>
        login
      </button>
      <div data-testid="authed">{String(auth.isAuthenticated)}</div>
      {auth.principal ? <div data-testid="email">{auth.principal.email}</div> : null}
      <RequireRole role="admin" fallback={<div data-testid="denied">denied</div>}>
        <div data-testid="admin-area">admin area</div>
      </RequireRole>
      <AdminPing />
    </div>
  );
};

const renderApp = (opts?: { onAuthExpired?: () => void }) => {
  const queryClient = createQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider onAuthExpired={opts?.onAuthExpired}>
          <Harness />
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
};

describe("AuthProvider — cookie-mode lifecycle", () => {
  it("login sends X-Auth-Mode: cookie, stores the token in memory, and surfaces the /auth/me principal", async () => {
    server.use(loginHandler(), meHandler(), http.get(`${ORIGIN}/admin/ping`, () =>
      HttpResponse.json({ status: "ok" }, { status: 200 }),
    ));
    const user = userEvent.setup();
    renderApp();

    expect(screen.getByTestId("authed")).toHaveTextContent("false");
    expect(screen.getByTestId("denied")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "login" }));

    await waitFor(() => expect(screen.getByTestId("authed")).toHaveTextContent("true"));
    // login selected cookie mode on the wire.
    expect(loginAuthMode).toBe("cookie");
    // access token held in memory (the getter the mutator reads).
    expect(getAccessToken()).toBe(TOKEN_A);
    // principal surfaced from /auth/me (which required the Bearer token).
    expect(await screen.findByTestId("email")).toHaveTextContent("user@example.com");
    // admin role decoded → RequireRole renders its children.
    expect(screen.getByTestId("admin-area")).toBeInTheDocument();
  });

  it("a 401 from a non-auth call triggers exactly one refresh (with the CSRF echo) and the call retries", async () => {
    // /admin/ping 401s until it sees the rotated TOKEN_B in the Authorization
    // header — proving the retry went out with the refreshed token.
    server.use(
      loginHandler(),
      meHandler(),
      refreshOkHandler(),
      http.get(`${ORIGIN}/admin/ping`, ({ request }) =>
        request.headers.get("Authorization") === `Bearer ${TOKEN_B}`
          ? HttpResponse.json({ status: "ok" }, { status: 200 })
          : unauthorized(),
      ),
    );
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(screen.getByTestId("authed")).toHaveTextContent("true"));

    // The initial ping (with TOKEN_A) 401s → single refresh → rotated token →
    // invalidate → ping refetches with TOKEN_B → success.
    await waitFor(() => expect(screen.getByTestId("ping")).toHaveTextContent("ping-ok"));
    expect(refreshCount).toBe(1);
    expect(refreshCsrfHeader).toBe(CSRF); // double-submit echo happened
    expect(getAccessToken()).toBe(TOKEN_B); // rotation stored
  });

  it("a 401 from the refresh itself clears auth and fires onAuthExpired", async () => {
    const onAuthExpired = vi.fn();
    server.use(
      loginHandler(),
      meHandler(),
      // Refresh is rejected (reuse-detected / expired family).
      http.post(`${ORIGIN}/auth/refresh`, () => {
        refreshCount += 1;
        return unauthorized();
      }),
      // /admin/ping always 401s, so it will drive the (doomed) refresh.
      http.get(`${ORIGIN}/admin/ping`, () => unauthorized()),
    );
    const user = userEvent.setup();
    renderApp({ onAuthExpired });

    await user.click(screen.getByRole("button", { name: "login" }));

    // login → ping 401 → refresh → refresh 401 → clear + onAuthExpired. The
    // whole cycle can complete before the first assertion runs, so assert only
    // the terminal state, not the transient logged-in moment.
    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("authed")).toHaveTextContent("false"));
    expect(refreshCount).toBe(1);
    expect(getAccessToken()).toBeNull();
  });
});
