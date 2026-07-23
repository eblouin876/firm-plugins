"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { RequireAuth } from "@repo/web-shared";

/**
 * Thin Next.js adapter over web-shared's `RequireAuth` render-gate. `RequireAuth`
 * is deliberately router-agnostic (it renders `children` when authenticated,
 * else its `fallback`, and never navigates) — the direct analog of the Vite
 * SPA's `ProtectedRoute.tsx`, which supplies a react-router `<Navigate>` as
 * that fallback. There's no App Router equivalent of `<Navigate>` (no
 * declarative redirect element), so the fallback here is a small child
 * component that fires `useRouter().replace("/login")` in an effect instead.
 * The client gate is UX only: the real gate is the backend's 401 on every
 * protected call.
 */
export const ProtectedGate = ({ children }: { children: ReactNode }): ReactNode => (
  <RequireAuth fallback={<RedirectToLogin />}>{children}</RequireAuth>
);

const RedirectToLogin = (): ReactNode => {
  const router = useRouter();
  // isPending covers the brief window right after a fresh page load where
  // AuthProvider hasn't resolved yet — but AuthProvider's isAuthenticated is
  // driven purely by the in-memory access token, which is never persisted
  // across a reload, so a fresh load is genuinely logged-out here. Redirect
  // unconditionally; there's no "still checking" state to wait out.
  useEffect(() => {
    router.replace("/login");
  }, [router]);
  return null;
};
