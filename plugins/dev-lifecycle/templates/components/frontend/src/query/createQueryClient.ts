import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { isApiError } from "../errors/ApiError";
import { addExpiredListener, requestRefresh } from "../auth/authBridge";

export interface CreateQueryClientOptions {
  /**
   * Called on a 401 `ApiError` from any query or mutation. Defaults to driving
   * the AuthProvider's single-flight `refresh` through the internal auth
   * bridge, so the app usually passes nothing. Override for custom wiring or
   * tests.
   */
  onAuthRefresh?: () => void;
  /**
   * Called when auth is ultimately unrecoverable (a refresh itself failed).
   * Registered as an expiry listener alongside AuthProvider's own
   * `onAuthExpired` prop — both fire. Use it for a cache-layer reaction
   * (e.g. `queryClient.clear()`), distinct from the app's redirect.
   */
  onAuthExpired?: () => void;
}

/**
 * A `QueryClient` with the kit's sane defaults and the auth-aware error wiring.
 *
 * - **No retry on 401/403.** A 401 is handled by the refresh flow below (a
 *   retry would just burn a request against a token that's already being
 *   rotated); a 403 is a real permission answer, not a transient fault. Other
 *   errors retry twice.
 * - **QueryCache + MutationCache `onError`.** On a 401 `ApiError` (which only
 *   reaches here because a `queryFn`/`mutationFn` used `unwrap` to throw it),
 *   the injected `onAuthRefresh` runs — by default `requestRefresh()`, the
 *   bridge into AuthProvider's single-flight refresh.
 */
export const createQueryClient = (options: CreateQueryClientOptions = {}): QueryClient => {
  const handleAuthError = (error: unknown): void => {
    if (!isApiError(error)) return;
    if (error.status === 401) {
      if (options.onAuthRefresh) options.onAuthRefresh();
      else void requestRefresh();
    }
  };

  if (options.onAuthExpired) {
    addExpiredListener(options.onAuthExpired);
  }

  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if (isApiError(error) && (error.status === 401 || error.status === 403)) return false;
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
    queryCache: new QueryCache({ onError: handleAuthError }),
    mutationCache: new MutationCache({ onError: handleAuthError }),
  });
};
