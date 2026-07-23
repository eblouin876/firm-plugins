import type { ReactNode } from "react";
import { Link, Outlet, useNavigate } from "react-router";
import { useAuth } from "@repo/web-shared";

/**
 * The authenticated app shell (a react-router layout route element): a header
 * with nav + the current principal + logout, then the routed `<Outlet />`.
 *
 * It is mounted BEHIND `ProtectedRoute` in the router, so it only ever renders
 * for a logged-in session — `useAuth().principal` (from `GET /auth/me`) is
 * expected to be present, though it may briefly be null while that query
 * resolves right after login.
 */
export const App = (): ReactNode => {
  const { principal, logout, isPending, hasRole } = useAuth();
  const navigate = useNavigate();

  const onLogout = async (): Promise<void> => {
    await logout();
    void navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3">
          <nav className="flex items-center gap-4 text-sm font-medium">
            <Link to="/" className="hover:text-primary">
              Dashboard
            </Link>
            {hasRole("admin") && (
              <Link to="/admin" className="hover:text-primary">
                Admin
              </Link>
            )}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            {principal && <span className="text-muted">{principal.email}</span>}
            <button
              type="button"
              onClick={() => void onLogout()}
              disabled={isPending}
              className="rounded-md border border-border px-3 py-1.5 font-medium hover:bg-bg disabled:opacity-60"
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
};
