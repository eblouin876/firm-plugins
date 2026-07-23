"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@repo/web-shared";
import { ProtectedGate } from "../../components/auth/ProtectedGate";
import { AdminGate } from "../../components/auth/AdminGate";

/**
 * The authenticated app shell — and, unlike the `web` app (where `AdminGate`
 * wraps only its `/admin` route), this is the **whole-app admin gate**: this
 * layout wraps `{children}` in `<ProtectedGate><AdminGate>…</AdminGate></ProtectedGate>`,
 * so EVERY route under `app/(app)/` — dashboard, users, moderation, blog —
 * only ever renders for a logged-in session that also carries the decoded
 * `admin` role claim. That's the defining design choice of this whole block
 * (see the README's "Whole-app admin gate" section): the admin tool has no
 * "logged in but not admin" screen to fall back to, because there's nothing
 * in this app a non-admin should ever see.
 *
 * Both gates are UX-only (an unverified/decoded JWT claim) — the
 * AUTHORITATIVE check is the backend's 401/403 on every call, which is why
 * the dashboard's `/admin/ping` call renders both the success and the 403
 * branch explicitly (see `app/(app)/dashboard/page.tsx`).
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedGate>
      <AdminGate>
        <AdminShell>{children}</AdminShell>
      </AdminGate>
    </ProtectedGate>
  );
}

// The nav's feature pages, all admin-gated by inheriting this layout.
// `/users` shipped real user-management UI in Stage 13b (see
// app/(app)/users/page.tsx); `/blog` shipped real posts CRUD + the TipTap
// editor in Stage 13d (see app/(app)/blog/page.tsx). `/moderation` remains a
// placeholder "coming in 13c" screen for now.
const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/users", label: "Users" },
  { href: "/moderation", label: "Moderation" },
  { href: "/blog", label: "Blog" },
] as const;

const AdminShell = ({ children }: { children: ReactNode }): ReactNode => {
  const { principal, logout, isPending } = useAuth();
  const router = useRouter();

  const onLogout = async (): Promise<void> => {
    await logout();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="mx-auto flex min-h-screen max-w-6xl">
        <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface px-4 py-6">
          <div className="mb-6 px-2 text-lg font-semibold tracking-tight">Admin</div>
          <nav className="flex flex-1 flex-col gap-1 text-sm font-medium">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="rounded-md px-2 py-1.5 hover:bg-bg hover:text-primary"
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="mt-6 flex flex-col gap-2 border-t border-border pt-4 text-sm">
            {principal && <span className="truncate px-2 text-muted">{principal.email}</span>}
            <button
              type="button"
              onClick={() => void onLogout()}
              disabled={isPending}
              className="rounded-md border border-border px-3 py-1.5 font-medium hover:bg-bg disabled:opacity-60"
            >
              Log out
            </button>
          </div>
        </aside>
        <main className="flex-1 px-8 py-8">{children}</main>
      </div>
    </div>
  );
};
