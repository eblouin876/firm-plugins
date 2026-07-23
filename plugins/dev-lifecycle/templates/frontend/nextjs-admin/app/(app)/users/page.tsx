import type { ReactNode } from "react";
import { ComingSoon } from "../../../components/ComingSoon";

// Stub feature page — resolves the "Users" nav link and proves the route
// builds, admin-gated purely by inheriting `app/(app)/layout.tsx`'s whole-app
// <ProtectedGate><AdminGate>. Real user-management UI (list/search/role
// edits) lands with a LATER stage (13b/13c) once the backend admin
// user-management endpoints exist — none do yet, this is foundation only.
export default function UsersPage(): ReactNode {
  return <ComingSoon title="Users" note="User management lands in a later admin-tool stage." />;
}
