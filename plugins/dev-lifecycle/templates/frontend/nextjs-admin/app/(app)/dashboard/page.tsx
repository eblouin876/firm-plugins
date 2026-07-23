"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminPingAdminPingGet, getAdminPingAdminPingGetQueryKey } from "@repo/api-client";
import { ApiError, isApiError, unwrap, useAuth } from "@repo/web-shared";
import { Banner } from "../../../components/form";

/**
 * The admin tool's landing screen — reached at `/dashboard` (this app's `/`
 * just redirects here) once `<ProtectedGate><AdminGate>` (the whole-app gate
 * in `app/(app)/layout.tsx`) has let the request through. Greets the admin
 * principal (`GET /auth/me`, loaded by web-shared's `AuthProvider`), then
 * fires a **live admin-gated call to `GET /admin/ping`** — this is Stage 13a's
 * acceptance anchor, proving end-to-end that this app's cookie-mode auth +
 * whole-app admin gate actually reaches an admin-only backend endpoint and
 * gets a real answer, not just a client-side role check.
 *
 * Same "render both branches" posture as the `web` app's `admin/page.tsx`
 * this is ported from: the CLIENT gate (`AdminGate`, an unverified decoded
 * JWT claim) is UX only, so this screen renders BOTH the 200 success (the
 * ping payload) AND the 403 branch explicitly, since a stale/forged `admin`
 * claim would land here and get a real 403 from the server — the
 * authoritative gate.
 */
export default function DashboardPage(): ReactNode {
  const { principal } = useAuth();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-muted">
          {principal ? (
            <>
              Signed in as <span className="font-medium text-text">{principal.email}</span>.
            </>
          ) : (
            "Loading your account…"
          )}
        </p>
      </div>

      <AdminPingCheck />
    </div>
  );
}

const AdminPingCheck = (): ReactNode => {
  const query = useQuery({
    queryKey: getAdminPingAdminPingGetQueryKey(),
    queryFn: async () => unwrap(await adminPingAdminPingGet()),
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-muted">Admin access check</h2>
      <p className="mt-1 text-sm text-muted">
        Live call to <span className="font-mono">GET /admin/ping</span> — proves this app's
        cookie-mode auth reaches an admin-gated backend endpoint end to end.
      </p>
      <div className="mt-3">
        {query.isPending && <Banner tone="info">Checking admin access…</Banner>}
        {query.isSuccess && (
          <Banner tone="success">
            Admin ping OK — server status: <span className="font-mono">{query.data.status}</span>
          </Banner>
        )}
        {query.isError && <AdminError error={query.error} />}
      </div>
    </div>
  );
};

/** Distinguish the real server gate (403) from other failures. */
const AdminError = ({ error }: { error: unknown }): ReactNode => {
  if (isApiError(error) && error.status === 403) {
    return (
      <Banner tone="error">
        Your account doesn&apos;t have admin access. (The server rejected the request with 403 —
        this is the real gate, regardless of what the client-side role check shows.)
      </Banner>
    );
  }
  return (
    <Banner tone="error">
      {error instanceof ApiError ? error.message : "Couldn't reach the admin endpoint."}
    </Banner>
  );
};
