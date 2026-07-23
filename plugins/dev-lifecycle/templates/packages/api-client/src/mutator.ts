/**
 * Custom fetch mutator for orval's React Query + fetch client mode.
 *
 * Orval's generated hooks call this with (url, options) and expect the
 * returned value to already be shaped `{ data, status, headers }` — the
 * generated response types (e.g. `createItemItemsPostResponse`) are unions
 * keyed on `status`, so callers pattern-match on `.status` instead of a
 * thrown error for documented non-2xx responses (e.g. a 422 validation
 * error). A rejected promise here is reserved for things the OpenAPI
 * contract can't describe: a network failure or an unparseable response.
 * Generated files import this module's `customFetch` by name — that import
 * contract is fixed by orval's mutator override and must not change shape.
 *
 * Base URL: injected via `configureApiClient({ baseUrl })`, called once at
 * app startup — deliberately NOT read from `process.env` at module load.
 * That would break every documented consumer: Vite ships no `process`
 * global in the browser bundle (a bare `process.env.X` throws
 * `ReferenceError: process is not defined` at import time), and Next/Expo
 * only statically inline framework-prefixed env vars
 * (`NEXT_PUBLIC_*`/`EXPO_PUBLIC_*`) — a bare `API_BASE_URL` read there
 * silently becomes `""` even when the var is set in the environment. See
 * the README's "Configuration" section for each consumer's exact wiring.
 * Unconfigured (or configured with `baseUrl: ""`) resolves to same-origin
 * relative URLs, a sane default behind a reverse proxy that forwards API
 * paths to the backend.
 *
 * Web cookie mode (Stage 5d): OFF by default — the default is BEARER mode,
 * so mobile/Expo (tokens in SecureStore, `Authorization: Bearer`) and every
 * existing call site are byte-for-byte unchanged. When a browser consumer
 * opts in with `configureApiClient({ baseUrl, cookieMode: true })`, three
 * things switch on for the cookie/CSRF web seam the backend's cookie mode
 * expects (see `references/wiring/auth-end-to-end.md`):
 *   1. every request sends `credentials: "include"`, so the browser
 *      attaches the backend's `HttpOnly` `refresh_token` cookie (scoped
 *      `Path=/auth`) and the non-HttpOnly `csrf_token` cookie;
 *   2. the login request (`POST /auth/login`) carries `X-Auth-Mode: cookie`,
 *      which is how the backend selects cookie mode at login (absent/any
 *      other value = bearer);
 *   3. the two cookie-authenticated state-changing auth calls
 *      (`POST /auth/refresh`, `POST /auth/logout`) echo the `csrf_token`
 *      cookie's value back as the `X-CSRF-Token` header — the client half
 *      of the backend's double-submit CSRF check.
 * The access token still lives only in the consumer's memory and travels in
 * the `Authorization` header exactly as in bearer mode; only the refresh
 * token moves into the `HttpOnly` cookie. Reading `csrf_token` requires
 * `document.cookie`, so the CSRF echo is a no-op under SSR / any runtime
 * without a `document` (React Native, Node) — safe because those runtimes
 * are bearer-mode targets that never set a CSRF cookie in the first place.
 */

export type ApiClientResponse<T = unknown> = {
  data: T;
  status: number;
  headers: Headers;
};

type ApiClientConfig = {
  /** Backend origin prepended to every generated request path. Trailing
   * slash(es) are trimmed. Empty string (the default) resolves to
   * same-origin relative URLs. */
  baseUrl: string;
  /** Opt into the browser cookie/CSRF web seam (default `false` = bearer
   * mode). See this module's header and the README's "Cookie mode (web)"
   * section. */
  cookieMode?: boolean;
  /** Optional access-token getter (default-off). When supplied AND a request
   * does not already carry its own `Authorization` header, the mutator
   * injects `Authorization: Bearer ${getAccessToken()}` — but only when the
   * getter returns a non-empty string (a `null`/`""` return injects
   * nothing). This is the seam a consumer that keeps the short-lived access
   * token in memory (e.g. `@repo/web-shared`'s `AuthProvider`, which wires
   * its in-memory token ref's getter in here) uses so the token rides every
   * generated call in BOTH bearer and cookie mode, without any generated
   * hook or call site having to thread the header through by hand. It never
   * clobbers a caller-supplied `Authorization` header, so an explicit
   * per-call override still wins. Omitted (the default) = the mutator sets
   * no `Authorization` header itself, exactly as before. */
  getAccessToken?: () => string | null;
};

const NO_TOKEN = (): string | null => null;

let config: Required<ApiClientConfig> = {
  baseUrl: "",
  cookieMode: false,
  getAccessToken: NO_TOKEN,
};

/**
 * Configure the shared api-client. Call once at app startup, before any
 * generated hook fires a request — see the README's "Configuration"
 * section for per-consumer wiring. Replaces the config wholesale, so it
 * also doubles as a reset (e.g. between test cases). `cookieMode` is
 * optional and defaults to `false`, so existing `configureApiClient({
 * baseUrl })` call sites keep bearer-mode behavior unchanged.
 */
export const configureApiClient = (next: ApiClientConfig): void => {
  config = {
    baseUrl: next.baseUrl.replace(/\/+$/, ""),
    cookieMode: next.cookieMode ?? false,
    getAccessToken: next.getAccessToken ?? NO_TOKEN,
  };
};

// Cookie-authenticated auth endpoints. Login is where the mode is selected
// (`X-Auth-Mode: cookie`); refresh/logout are the state-changing calls the
// backend guards with double-submit CSRF when the refresh cookie is present.
const AUTH_LOGIN_PATH = "/auth/login";
const AUTH_CSRF_PATHS = new Set(["/auth/refresh", "/auth/logout"]);

/**
 * Read the non-HttpOnly `csrf_token` cookie the backend set alongside the
 * `HttpOnly` refresh cookie. Returns `null` (a safe no-op for the caller)
 * when there is no `document` — SSR, React Native, or any non-browser
 * runtime — or when the cookie is simply absent.
 */
const readCsrfCookie = (): string | null => {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match?.[1] != null ? decodeURIComponent(match[1]) : null;
};

export const customFetch = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const headers = new Headers(options.headers);
  if (options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Access-token injection (default-off): only when a getter was configured,
  // the caller didn't already set Authorization, and the getter returns a
  // non-empty token. Runs in both bearer and cookie mode.
  if (!headers.has("Authorization")) {
    const token = config.getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = { ...options, headers };

  if (config.cookieMode) {
    // Attach the browser's cookies (refresh_token / csrf_token) to every
    // request; both are path-scoped by the backend, so this is harmless on
    // non-auth paths and required on the /auth/* ones.
    init.credentials = "include";

    // Match on the request PATH only (strip any query/hash) — `url` is the
    // generated path, never carrying the configured baseUrl.
    const path = url.split(/[?#]/)[0] ?? url;
    const method = (options.method ?? "GET").toUpperCase();

    if (path === AUTH_LOGIN_PATH) {
      // Select cookie mode at login. Absent/any-other value = bearer.
      headers.set("X-Auth-Mode", "cookie");
    } else if (
      AUTH_CSRF_PATHS.has(path) &&
      method !== "GET" &&
      method !== "HEAD" &&
      !headers.has("X-CSRF-Token")
    ) {
      // Double-submit echo: send the csrf_token cookie back as a header.
      const csrf = readCsrfCookie();
      if (csrf != null) headers.set("X-CSRF-Token", csrf);
    }
  }

  const response = await fetch(`${config.baseUrl}${url}`, init);

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : ((await response.text()) as unknown);

  return {
    data,
    status: response.status,
    headers: response.headers,
  } as T;
};
