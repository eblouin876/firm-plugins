import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuth } from "@repo/web-shared";
import { Banner } from "../components/form";

/**
 * The authenticated landing screen. Renders the principal resolved from
 * `GET /auth/me` (loaded by web-shared's `AuthProvider`) plus the UX-only roles
 * decoded from the access token. Roles here are for display/affordances only —
 * the `/admin` link works because the server enforces the role, not because
 * this list says so.
 */
export const DashboardPage = (): ReactNode => {
  const { principal, claims, hasRole } = useAuth();

  if (!principal) {
    return <Banner tone="info">Loading your account…</Banner>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-muted">You&apos;re signed in.</p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm">
        <dt className="font-medium text-muted">User ID</dt>
        <dd className="font-mono break-all">{principal.id}</dd>
        <dt className="font-medium text-muted">Email</dt>
        <dd>{principal.email}</dd>
        <dt className="font-medium text-muted">Roles</dt>
        <dd>{claims.roles.length > 0 ? claims.roles.join(", ") : "—"}</dd>
      </dl>

      {hasRole("admin") && (
        <p className="text-sm">
          You have admin access.{" "}
          <Link className="text-primary hover:underline" to="/admin">
            Open the admin area
          </Link>
        </p>
      )}
    </div>
  );
};
