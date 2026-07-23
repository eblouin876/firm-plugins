import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { RequireRole } from "@repo/web-shared";

/**
 * Thin router adapter over web-shared's `RequireRole` render-gate, pinned to
 * the `"admin"` role. Same contract as ProtectedRoute: the guard renders
 * `children` when the decoded access-token `roles` claim includes `admin`, else
 * this app's `<Navigate>` redirect. This is UX gating on an UNVERIFIED claim —
 * the authoritative check is the backend's 403 on `GET /admin/ping`, which the
 * admin screen also renders (see AdminPage).
 */
export const AdminRoute = ({ children }: { children: ReactNode }): ReactNode => (
  <RequireRole role="admin" fallback={<Navigate to="/" replace />}>
    {children}
  </RequireRole>
);
