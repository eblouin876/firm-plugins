"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@repo/web-shared";

/**
 * Thin Next.js adapter over web-shared's `RequireRole` render-gate, pinned to
 * the `"admin"` role. Same contract as `ProtectedGate`: the guard renders
 * `children` when the decoded access-token `roles` claim includes `admin`,
 * else redirects. This is UX gating on an UNVERIFIED claim — the
 * authoritative check is the backend's 403 on `GET /admin/ping`, which the
 * dashboard screen also renders (see `app/(app)/dashboard/page.tsx`).
 *
 * Unlike the `web` app (where this gate wraps only `/admin`), this block's
 * `app/(app)/layout.tsx` wraps the WHOLE authenticated route tree in this
 * gate — the whole-app admin gate that defines this block. A consequence
 * worth naming: the fallback below redirects a non-admin to `/dashboard`,
 * but `/dashboard` is itself inside the gated tree, so a signed-in
 * non-admin just gets redirected back to the page they're already on (a
 * no-op navigation, not a loop) and never sees any gated content — this app
 * has nowhere valid for them to go, which is the intended, fully-locked-out
 * posture for a tool that is admin-only end to end.
 */
export const AdminGate = ({ children }: { children: ReactNode }): ReactNode => (
  <RequireRole role="admin" fallback={<RedirectToDashboard />}>
    {children}
  </RequireRole>
);

const RedirectToDashboard = (): ReactNode => {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);
  return null;
};
