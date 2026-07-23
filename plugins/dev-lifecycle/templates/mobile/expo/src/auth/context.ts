/**
 * The auth React context object + its value type, split into their own module
 * so both AuthProvider (which creates the Provider) and useAuth (which reads it)
 * import from here without a cycle.
 */
import { createContext } from "react";

import type { AuthStatus, AuthorizedResponse } from "./authEngine";

export interface AuthContextValue {
  status: AuthStatus;
  /** Roles from the access token's `roles` claim — the RBAC claim the backend
   * gates on; rendered on the landing screen as end-to-end proof. */
  roles: string[];
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
  /** Run a protected request with the bearer header + 401 refresh/retry. Pass a
   * function that forwards the `RequestInit` to a generated client call. */
  authorizedRequest<T>(
    call: (init: RequestInit) => Promise<AuthorizedResponse<T>>,
  ): Promise<AuthorizedResponse<T>>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
