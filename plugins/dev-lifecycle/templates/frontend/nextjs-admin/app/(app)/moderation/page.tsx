import type { ReactNode } from "react";
import { ComingSoon } from "../../../components/ComingSoon";

// Stub feature page — resolves the "Moderation" nav link and proves the route
// builds, admin-gated purely by inheriting `app/(app)/layout.tsx`'s whole-app
// <ProtectedGate><AdminGate>. Real moderation UI (queues, actions) lands with
// a LATER stage (13b/13c) once the backend moderation endpoints exist — none
// do yet, this is foundation only.
export default function ModerationPage(): ReactNode {
  return (
    <ComingSoon title="Moderation" note="Moderation tooling lands in a later admin-tool stage." />
  );
}
