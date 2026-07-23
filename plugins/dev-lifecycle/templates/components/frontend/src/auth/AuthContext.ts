import { createContext } from "react";
import type { PrincipalOut } from "@repo/api-client";
import type { AccessTokenClaims } from "../jwt/decodeAccessTokenClaims";

export interface AuthState {
  /** True once an access token is held in memory (i.e. logged in this tab). */
  isAuthenticated: boolean;
  /** UX-only claims (roles/sub) decoded from the current access token. Empty
   *  when logged out. The REAL authorization gate is always the server 403. */
  claims: AccessTokenClaims;
  /** The principal resolved from `GET /auth/me` (id + email), or null. */
  principal: PrincipalOut | null;
  /** True while a login, refresh, or logout call is in flight. */
  isPending: boolean;
}

export interface AuthContextValue extends AuthState {
  /** Log in (cookie mode): stores the access token in memory, decodes roles,
   *  and loads the principal. Throws an `ApiError` on bad credentials (401) or
   *  a validation failure (422) for the caller's form to surface. */
  login: (email: string, password: string) => Promise<void>;
  /** Log out: best-effort server call, then clears in-memory token + query cache. */
  logout: () => Promise<void>;
  /** Single-flight token refresh. Resolves true if rotated, false if the
   *  session is unrecoverable (memory cleared + `onAuthExpired` fired). */
  refresh: () => Promise<boolean>;
  /** UX-only role check against the decoded `roles` claim. */
  hasRole: (role: string) => boolean;
}

/** Null outside a provider — `useAuth` throws a clear error in that case. */
export const AuthContext = createContext<AuthContextValue | null>(null);
