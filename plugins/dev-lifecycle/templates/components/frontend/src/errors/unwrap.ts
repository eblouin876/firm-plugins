import { ApiError } from "./ApiError";
import { isErrorEnvelope } from "./errorEnvelope";

/** The `{ data, status, headers }` shape every @repo/api-client call resolves to. */
export interface ApiResult<T> {
  data: T;
  status: number;
  headers: Headers;
}

/**
 * THE seam that makes react-query treat orval's "401-as-data" as an error.
 *
 * Orval's fetch client resolves a documented non-2xx (a 401, a 422) as a
 * fulfilled promise `{ data, status }` — it does NOT throw. A `queryFn` /
 * `mutationFn` that returns that value therefore looks like SUCCESS to
 * react-query, so the QueryCache `onError` (and thus the 401 → refresh flow)
 * never fires. Wrap the generated call in `unwrap` so a non-2xx throws an
 * `ApiError` instead:
 *
 *     useQuery({ queryKey, queryFn: async () => unwrap(await meAuthMeGet()) })
 *
 * On a 2xx it returns `res.data` unchanged; otherwise it throws an `ApiError`
 * carrying the status and (when the body parsed as one) the `ErrorEnvelope`.
 */
export const unwrap = <T>(res: ApiResult<T>): T => {
  if (res.status >= 200 && res.status < 300) return res.data;
  throw new ApiError(res.status, isErrorEnvelope(res.data) ? res.data : undefined);
};
