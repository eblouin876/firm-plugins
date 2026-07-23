import type { ReactNode } from "react";
import { useAuth } from "./useAuth";

interface RequireAuthProps {
  children: ReactNode;
  /**
   * Rendered instead of `children` when not authenticated. These guards are
   * RENDER-GATE primitives — they never navigate. The app supplies a router
   * redirect as the fallback (e.g. `<Navigate to="/login" replace />` with
   * react-router in the Vite app), keeping this package router-agnostic.
   * Defaults to rendering nothing.
   */
  fallback?: ReactNode;
}

/** Render `children` only when authenticated; otherwise render `fallback`. */
export const RequireAuth = ({ children, fallback = null }: RequireAuthProps): ReactNode => {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : fallback;
};

interface RequireRoleProps {
  /** A required role, or a set of roles of which the user needs at least one. */
  role: string | string[];
  children: ReactNode;
  /** Rendered when the user lacks the role(s) (or isn't authenticated). Same
   *  render-gate contract as `RequireAuth` — the app supplies any redirect. */
  fallback?: ReactNode;
}

/**
 * Render `children` only when the user is authenticated AND holds at least one
 * of the required roles. UX gating only — the decoded roles are unverified, so
 * the server's 403 on the underlying call is the real gate (see
 * `decodeAccessTokenClaims`).
 */
export const RequireRole = ({ role, children, fallback = null }: RequireRoleProps): ReactNode => {
  const { isAuthenticated, hasRole } = useAuth();
  const required = Array.isArray(role) ? role : [role];
  const allowed = isAuthenticated && required.some((r) => hasRole(r));
  return allowed ? children : fallback;
};
