/**
 * Framework-free auth engine — the mobile (BEARER) half of
 * `references/wiring/auth-end-to-end.md`, with zero React / Expo / api-client
 * imports so it can be unit-tested against a fake storage + a stubbed API
 * (see authEngine.test.ts). The React layer (AuthProvider) and the native
 * storage (secureStore.ts) and the generated client (authApi.ts) are injected;
 * this module owns only the token state machine:
 *
 *   - access token in MEMORY (never persisted);
 *   - refresh token in the injected `storage` (SecureStore in the real app);
 *   - `authorizedRequest` attaches `Authorization: Bearer <access>` and, on a
 *     401, runs a SINGLE-FLIGHT refresh + exactly ONE retry;
 *   - every successful refresh returns a NEW refresh token → storage is
 *     overwritten immediately (rotation / reuse-detection);
 *   - a refresh that does not return 200 is TERMINAL → clear storage + memory,
 *     status → unauthenticated (the React layer redirects to login);
 *   - logout best-effort POSTs the refresh token, then UNCONDITIONALLY clears.
 */

/** Where the refresh token lives. SecureStore in the app; a fake in tests. */
export interface TokenStorage {
  get(): Promise<string | null>;
  set(token: string): Promise<void>;
  clear(): Promise<void>;
}

/** Normalized result of an auth-lifecycle call, decoupled from the generated
 * client's response union. `accessToken`/`refreshToken` are non-null only on a
 * 200. */
export interface TokenResult {
  status: number;
  accessToken: string | null;
  refreshToken: string | null;
}

/** The three bearer-mode auth calls, injected so the engine never imports the
 * generated client (the real impl lives in authApi.ts). Login/refresh/logout
 * carry their token in the request BODY — no bearer header, no cookie, no
 * CSRF. */
export interface AuthApi {
  login(email: string, password: string): Promise<TokenResult>;
  refresh(refreshToken: string): Promise<TokenResult>;
  logout(refreshToken: string): Promise<void>;
}

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/** The public, subscribable snapshot the React layer renders. */
export interface AuthSnapshot {
  status: AuthStatus;
  roles: string[];
}

/** Minimal shape of a protected-endpoint call result the engine inspects. */
export interface AuthorizedResponse<T> {
  status: number;
  data?: T;
}

export interface AuthEngine {
  getSnapshot(): AuthSnapshot;
  subscribe(listener: () => void): () => void;
  /** Cold-start: read the stored refresh token and, if present, refresh to a
   * live access token — otherwise settle on `unauthenticated`. */
  bootstrap(): Promise<void>;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
  /** Run a protected call with the bearer header attached; refresh + retry once
   * on 401. `call` receives the `RequestInit` to pass to a generated function
   * (e.g. `meAuthMeGet(init)`). */
  authorizedRequest<T>(
    call: (init: RequestInit) => Promise<AuthorizedResponse<T>>,
  ): Promise<AuthorizedResponse<T>>;
  /** AppState → active hook: refresh proactively if the access token is near
   * expiry, so the first post-resume request already carries a fresh token. */
  maybeProactiveRefresh(): Promise<void>;
}

/** Thrown by `login` when the credentials are rejected (non-200). */
export class AuthError extends Error {
  constructor(readonly status: number) {
    super(`auth request failed with status ${status}`);
    this.name = "AuthError";
  }
}

/** Refresh this many seconds BEFORE the access token's `exp`. */
const REFRESH_SKEW_SECONDS = 60;

function base64UrlToString(b64url: string): string {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  // `atob` is a global in Node 16+ (vitest) and Hermes / RN 0.74+ (device).
  const binary = atob(padded);
  return binary;
}

/** Decode a JWT's payload for `exp` (proactive-refresh timing) and the `roles`
 * claim (rendered on the landing screen — the RBAC claim the backend gates on).
 * Never throws: a malformed token yields empty roles / null exp. */
function decodeAccessToken(token: string): { exp: number | null; roles: string[] } {
  try {
    const payload = token.split(".")[1];
    if (payload == null) return { exp: null, roles: [] };
    const claims = JSON.parse(base64UrlToString(payload)) as {
      exp?: unknown;
      roles?: unknown;
    };
    const roles = Array.isArray(claims.roles)
      ? claims.roles.filter((r): r is string => typeof r === "string")
      : [];
    const exp = typeof claims.exp === "number" ? claims.exp : null;
    return { exp, roles };
  } catch {
    return { exp: null, roles: [] };
  }
}

export function createAuthEngine(deps: { storage: TokenStorage; api: AuthApi }): AuthEngine {
  const { storage, api } = deps;

  let accessToken: string | null = null;
  let accessExp: number | null = null;
  let roles: string[] = [];
  let status: AuthStatus = "loading";

  // Single-flight guard: concurrent 401s share ONE refresh, not N.
  let refreshInFlight: Promise<boolean> | null = null;

  const listeners = new Set<() => void>();
  let snapshot: AuthSnapshot = { status, roles };

  const emit = (): void => {
    snapshot = { status, roles };
    for (const listener of listeners) listener();
  };

  const authInit = (token: string): RequestInit => ({
    headers: { Authorization: `Bearer ${token}` },
  });

  const applyTokens = async (result: TokenResult): Promise<void> => {
    const decoded = decodeAccessToken(result.accessToken as string);
    accessToken = result.accessToken;
    accessExp = decoded.exp;
    roles = decoded.roles;
    // Rotation: overwrite the stored refresh token immediately with the newly
    // minted one, so a stolen/replayed prior token is already dead.
    await storage.set(result.refreshToken as string);
    status = "authenticated";
    emit();
  };

  const clearSession = async (): Promise<void> => {
    accessToken = null;
    accessExp = null;
    roles = [];
    await storage.clear();
    status = "unauthenticated";
    emit();
  };

  // Returns true if a live access token is now in memory, false if the session
  // was cleared (terminal). Single-flight.
  const doRefresh = (): Promise<boolean> => {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async () => {
      try {
        const stored = await storage.get();
        if (stored == null) {
          await clearSession();
          return false;
        }
        const result = await api.refresh(stored);
        if (result.status === 200 && result.accessToken != null && result.refreshToken != null) {
          await applyTokens(result);
          return true;
        }
        // A refresh-401 (or anything non-200) is terminal: the token family is
        // revoked backend-side; drop everything and force re-login.
        await clearSession();
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
    return refreshInFlight;
  };

  return {
    getSnapshot: () => snapshot,

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async bootstrap() {
      status = "loading";
      emit();
      const stored = await storage.get();
      if (stored == null) {
        status = "unauthenticated";
        emit();
        return;
      }
      await doRefresh();
    },

    async login(email, password) {
      const result = await api.login(email, password);
      if (result.status === 200 && result.accessToken != null && result.refreshToken != null) {
        await applyTokens(result);
        return;
      }
      throw new AuthError(result.status);
    },

    async logout() {
      const stored = await storage.get();
      if (stored != null) {
        // Best-effort: revoke the family server-side. Never block the local
        // clear on it — logout is idempotent and must always end signed-out.
        try {
          await api.logout(stored);
        } catch {
          /* ignore — clear unconditionally below */
        }
      }
      await clearSession();
    },

    async authorizedRequest(call) {
      let token = accessToken;
      if (token == null) {
        const ok = await doRefresh();
        if (!ok) return { status: 401 };
        token = accessToken as string;
      }
      const first = await call(authInit(token));
      if (first.status !== 401) return first;
      // 401 → single-flight refresh, then exactly one retry with the new token.
      const refreshed = await doRefresh();
      if (!refreshed) return first;
      return call(authInit(accessToken as string));
    },

    async maybeProactiveRefresh() {
      if (status !== "authenticated" || accessExp == null) return;
      const now = Math.floor(Date.now() / 1000);
      if (accessExp - now <= REFRESH_SKEW_SECONDS) {
        await doRefresh();
      }
    },
  };
}
