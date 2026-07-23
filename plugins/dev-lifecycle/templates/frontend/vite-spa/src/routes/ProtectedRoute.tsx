import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { RequireAuth } from "@repo/web-shared";

/**
 * Thin router adapter over web-shared's `RequireAuth` render-gate. `RequireAuth`
 * is deliberately router-agnostic (it renders `children` when authenticated,
 * else its `fallback`, and never navigates); this app supplies the concrete
 * redirect — a react-router `<Navigate>` to the login screen — as that
 * fallback. The client gate is UX only: the real gate is the backend's 401 on
 * every protected call.
 */
export const ProtectedRoute = ({ children }: { children: ReactNode }): ReactNode => (
  <RequireAuth fallback={<Navigate to="/login" replace />}>{children}</RequireAuth>
);
