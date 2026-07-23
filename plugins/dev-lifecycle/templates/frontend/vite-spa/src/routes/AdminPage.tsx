import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminPingAdminPingGet, getAdminPingAdminPingGetQueryKey } from "@repo/api-client";
import { ApiError, isApiError, unwrap } from "@repo/web-shared";
import { Banner } from "../components/form";

/**
 * The admin area. This route is reached through the `<AdminRoute>` client gate
 * (RequireRole "admin"), but the CLIENT gate is UX only — the AUTHORITATIVE
 * gate is the server's 403 on `GET /admin/ping`. So we call it and render BOTH
 * branches: the 200 success (the ping payload) AND the 403 "forbidden" answer,
 * the latter being what a user with a stale/forged `admin` claim actually hits.
 *
 * The `queryFn` wraps the generated `adminPingAdminPingGet` in `unwrap(...)`, so
 * a 401 throws an `ApiError` that drives web-shared's refresh flow (a 403 is a
 * real permission answer — the QueryClient deliberately does NOT refresh on it).
 * The query key is the generated one, so this shares cache with any other
 * caller of the same endpoint.
 */
export const AdminPage = (): ReactNode => {
  const query = useQuery({
    queryKey: getAdminPingAdminPingGetQueryKey(),
    queryFn: async () => unwrap(await adminPingAdminPingGet()),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Admin</h1>
        <p className="mt-1 text-muted">Role-gated area — the server verifies your access.</p>
      </div>

      {query.isPending && <Banner tone="info">Checking admin access…</Banner>}

      {query.isSuccess && (
        <Banner tone="success">
          Admin ping OK — server status: <span className="font-mono">{query.data.status}</span>
        </Banner>
      )}

      {query.isError && <AdminError error={query.error} />}
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
