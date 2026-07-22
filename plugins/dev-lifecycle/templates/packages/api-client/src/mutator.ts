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
};

let config: ApiClientConfig = { baseUrl: "" };

/**
 * Configure the shared api-client. Call once at app startup, before any
 * generated hook fires a request — see the README's "Configuration"
 * section for per-consumer wiring. Replaces the config wholesale, so it
 * also doubles as a reset (e.g. between test cases).
 */
export const configureApiClient = (next: ApiClientConfig): void => {
  config = { baseUrl: next.baseUrl.replace(/\/+$/, "") };
};

export const customFetch = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const headers = new Headers(options.headers);
  if (options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${config.baseUrl}${url}`, { ...options, headers });

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
