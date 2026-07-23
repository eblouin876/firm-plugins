import { ApiError } from "./ApiError";
import { isErrorEnvelope } from "./errorEnvelope";

/** The `{ data, status, headers }` shape every @repo/api-client call resolves to. */
export interface ApiResult<T> {
  data: T;
  status: number;
  headers: Headers;
}

type SuccessStatus = 200 | 201 | 202 | 203 | 204;

/**
 * The success payload type for a response. Orval's generated response type is a
 * discriminated union keyed on `status` (e.g. `{ data: HealthStatus; status:
 * 200 } | { data: ErrorEnvelope; status: 401 }`); `Extract` picks the 2xx
 * member(s) so `unwrap` returns just the success `data` (`HealthStatus`), not
 * the whole union. When there's no literal-2xx member (a plain `ApiResult<T>`
 * whose `status` is a bare `number`), it falls back to that `T`.
 */
type UnwrapData<R> = [Extract<R, { status: SuccessStatus }>] extends [never]
  ? R extends { data: infer D }
    ? D
    : never
  : Extract<R, { status: SuccessStatus }> extends { data: infer D }
    ? D
    : never;

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
export const unwrap = <R extends { status: number; data: unknown; headers: Headers }>(
  res: R,
): UnwrapData<R> => {
  if (res.status >= 200 && res.status < 300) return res.data as UnwrapData<R>;
  throw new ApiError(res.status, isErrorEnvelope(res.data) ? res.data : undefined);
};
