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
 *
 * Base URL: read from `API_BASE_URL` at call time — no hardcoded host.
 * Unset resolves to `""` (relative URLs), which is intentional for a same-
 * origin dev proxy; a real deployment always sets `API_BASE_URL`.
 */

export type ApiClientResponse<T = unknown> = {
  data: T;
  status: number;
  headers: Headers;
};

const BASE_URL = process.env.API_BASE_URL ?? "";

export const customFetch = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE_URL}${url}`, { ...options, headers });

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
