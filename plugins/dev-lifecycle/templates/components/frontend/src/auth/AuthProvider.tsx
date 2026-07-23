import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  useLoginAuthLoginPost,
  useLogoutAuthLogoutPost,
  useMeAuthMeGet,
  useRefreshAuthRefreshPost,
} from "@repo/api-client";
import type { PrincipalOut } from "@repo/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../errors/ApiError";
import { isErrorEnvelope } from "../errors/errorEnvelope";
import { decodeAccessTokenClaims } from "../jwt/decodeAccessTokenClaims";
import {
  addExpiredListener,
  clearRefreshHandler,
  notifyExpired,
  setAccessToken,
  setRefreshHandler,
} from "./authBridge";
import { AuthContext } from "./AuthContext";
import type { AuthContextValue } from "./AuthContext";

export interface AuthProviderProps {
  children: ReactNode;
  /**
   * Fired when a token refresh ultimately fails and the session is
   * unrecoverable — the app typically redirects to its login route here. Runs
   * AFTER in-memory auth state is cleared. (createQueryClient's `onAuthExpired`
   * option, if set, also fires — both are registered listeners.)
   */
  onAuthExpired?: () => void;
}

/**
 * The cookie-mode auth lifecycle from `references/wiring/auth-end-to-end.md`,
 * as a portable React provider. MUST be mounted inside a `QueryClientProvider`
 * (it uses the generated React Query hooks). The access token lives ONLY in
 * memory — a React state (for re-render) mirrored into the module-scoped auth
 * bridge (so the api-client mutator's `getAccessToken` and the QueryClient's
 * 401 handler can reach it). It is NEVER written to localStorage/sessionStorage;
 * the refresh token lives only in the backend's HttpOnly cookie and is never
 * seen by this code. The empty-string `refresh_token` in cookie-mode response
 * bodies is deliberately ignored.
 */
export const AuthProvider = ({ children, onAuthExpired }: AuthProviderProps): ReactNode => {
  const queryClient = useQueryClient();
  const { mutateAsync: loginAsync, isPending: loginPending } = useLoginAuthLoginPost();
  const { mutateAsync: refreshAsync, isPending: refreshPending } = useRefreshAuthRefreshPost();
  const { mutateAsync: logoutAsync, isPending: logoutPending } = useLogoutAuthLogoutPost();

  const [accessToken, setAccessTokenState] = useState<string | null>(null);

  const applyToken = useCallback((token: string): void => {
    setAccessTokenState(token);
    setAccessToken(token); // bridge → mutator getAccessToken + QueryClient
  }, []);

  const clearAuth = useCallback((): void => {
    setAccessTokenState(null);
    setAccessToken(null);
  }, []);

  // Principal from /auth/me — enabled only once a token is in memory, and only
  // read when it resolved 200 (a 401 here just means "no principal yet").
  const meQuery = useMeAuthMeGet({
    query: {
      enabled: accessToken !== null,
      retry: false,
      staleTime: Infinity,
    },
  });
  const meData = meQuery.data;
  const principal: PrincipalOut | null =
    meData && meData.status === 200 ? meData.data : null;

  const claims = useMemo(() => decodeAccessTokenClaims(accessToken), [accessToken]);

  // --- refresh: single-flight, rotation, invalidate ------------------------
  const inFlight = useRef<Promise<boolean> | null>(null);

  const doRefresh = useCallback(async (): Promise<boolean> => {
    try {
      const res = await refreshAsync({ data: { refresh_token: "" } });
      if (res.status === 200) {
        applyToken(res.data.access_token);
        // Rotated token in place; refetch everything so the failed call
        // retries with the new Authorization header.
        await queryClient.invalidateQueries();
        return true;
      }
      // Refresh itself was rejected (reuse-detected/expired family) → the
      // session is unrecoverable.
      clearAuth();
      notifyExpired();
      return false;
    } catch {
      clearAuth();
      notifyExpired();
      return false;
    }
  }, [refreshAsync, queryClient, applyToken, clearAuth]);

  const refresh = useCallback((): Promise<boolean> => {
    if (inFlight.current) return inFlight.current;
    const pending = doRefresh().finally(() => {
      inFlight.current = null;
    });
    inFlight.current = pending;
    return pending;
  }, [doRefresh]);

  // --- login / logout ------------------------------------------------------
  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      const res = await loginAsync({ data: { email, password } });
      if (res.status !== 200) {
        throw new ApiError(res.status, isErrorEnvelope(res.data) ? res.data : undefined);
      }
      applyToken(res.data.access_token);
    },
    [loginAsync, applyToken],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await logoutAsync({ data: { refresh_token: "" } });
    } finally {
      clearAuth();
      queryClient.clear();
    }
  }, [logoutAsync, clearAuth, queryClient]);

  const hasRole = useCallback((role: string): boolean => claims.roles.includes(role), [claims]);

  // --- bridge registration -------------------------------------------------
  useEffect(() => {
    setRefreshHandler(refresh);
    return () => {
      clearRefreshHandler();
    };
  }, [refresh]);

  useEffect(() => {
    if (!onAuthExpired) return;
    return addExpiredListener(onAuthExpired);
  }, [onAuthExpired]);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: accessToken !== null,
      claims,
      principal,
      isPending: loginPending || refreshPending || logoutPending,
      login,
      logout,
      refresh,
      hasRole,
    }),
    [
      accessToken,
      claims,
      principal,
      loginPending,
      refreshPending,
      logoutPending,
      login,
      logout,
      refresh,
      hasRole,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
