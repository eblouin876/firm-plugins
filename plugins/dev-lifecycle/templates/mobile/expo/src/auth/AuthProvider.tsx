/**
 * React binding for the framework-free auth engine. Holds ONE engine instance
 * (built with the real SecureStore seam + the generated-client adapter),
 * bootstraps it on mount, exposes its snapshot via `useSyncExternalStore`, and
 * wires the AppState → active proactive refresh. All token logic lives in the
 * engine (authEngine.ts) — this file is just the React/Expo surface.
 */
import { useEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from "react";
import { AppState, type AppStateStatus } from "react-native";

import {
  createAuthEngine,
  type AuthEngine,
  type AuthorizedResponse,
  type AuthStatus,
} from "./authEngine";
import { generatedAuthApi } from "./authApi";
import { refreshTokenStore } from "./secureStore";
import { AuthContext, type AuthContextValue } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  // One engine for the app's lifetime.
  const engineRef = useRef<AuthEngine | null>(null);
  if (engineRef.current == null) {
    engineRef.current = createAuthEngine({
      storage: refreshTokenStore,
      api: generatedAuthApi,
    });
  }
  const engine = engineRef.current;

  const snapshot = useSyncExternalStore(engine.subscribe, engine.getSnapshot);

  useEffect(() => {
    void engine.bootstrap();
  }, [engine]);

  // Proactively refresh a near-expiry access token when the app returns to the
  // foreground, so the first post-resume request already carries a fresh token.
  useEffect(() => {
    const onChange = (next: AppStateStatus): void => {
      if (next === "active") void engine.maybeProactiveRefresh();
    };
    const sub = AppState.addEventListener("change", onChange);
    return () => sub.remove();
  }, [engine]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status: snapshot.status,
      roles: snapshot.roles,
      login: (email: string, password: string) => engine.login(email, password),
      logout: () => engine.logout(),
      authorizedRequest: <T,>(call: (init: RequestInit) => Promise<AuthorizedResponse<T>>) =>
        engine.authorizedRequest(call),
    }),
    [engine, snapshot.status, snapshot.roles],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export type { AuthStatus };
