// The narrow, module-scoped channel between the in-memory auth state (owned by
// AuthProvider — see auth/AuthProvider) and the two consumers that must reach
// it WITHOUT a React context:
//   1. the api-client mutator's access-token getter (`configureApiClient({
//      getAccessToken })`), which runs outside React entirely; and
//   2. the QueryClient's `onError` refresh trigger (query/createQueryClient),
//      which fires from the cache, not a component.
//
// Module-scoped mutable state is safe here precisely because this state is
// browser-in-memory and CLIENT-ONLY: the access token is never persisted and
// never set during a server render, so on the server `getAccessToken()`
// returns null and nothing is injected. Only `getAccessToken` is a public
// export (the app wires it into `configureApiClient`); everything else is
// internal to @repo/web-shared and consumed by createQueryClient / AuthProvider.

let accessToken: string | null = null;
let refreshHandler: () => Promise<boolean> = async () => false;
const expiredListeners = new Set<() => void>();

/**
 * The getter the app passes to `configureApiClient({ getAccessToken })` so the
 * in-memory access token rides every generated request as a Bearer header.
 * Returns null when logged out (or on a server render). PUBLIC.
 */
export const getAccessToken = (): string | null => accessToken;

/** @internal AuthProvider writes the current in-memory access token here. */
export const setAccessToken = (token: string | null): void => {
  accessToken = token;
};

/** @internal AuthProvider registers its single-flight `refresh` here on mount. */
export const setRefreshHandler = (fn: () => Promise<boolean>): void => {
  refreshHandler = fn;
};

/** @internal AuthProvider clears its handler on unmount (back to a no-op). */
export const clearRefreshHandler = (): void => {
  refreshHandler = async () => false;
};

/**
 * @internal The QueryClient's `onError` calls this on a 401 to drive a single
 * refresh. Resolves `true` if the token was rotated, `false` if auth is
 * unrecoverable (the handler itself clears memory + notifies expiry first).
 */
export const requestRefresh = (): Promise<boolean> => refreshHandler();

/**
 * @internal Register an expiry listener; returns an unsubscribe fn. Used by
 * BOTH AuthProvider (its `onAuthExpired` prop) and createQueryClient (its
 * `onAuthExpired` option), so every registered hook fires when a refresh
 * ultimately fails — they don't compete, they all run.
 */
export const addExpiredListener = (fn: () => void): (() => void) => {
  expiredListeners.add(fn);
  return () => {
    expiredListeners.delete(fn);
  };
};

/** @internal AuthProvider calls this after clearing memory on a failed refresh. */
export const notifyExpired = (): void => {
  for (const fn of expiredListeners) fn();
};

/** @internal Test-only: reset all module state so cases don't leak into one another. */
export const __resetAuthBridge = (): void => {
  accessToken = null;
  refreshHandler = async () => false;
  expiredListeners.clear();
};
