"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getListAdminUsersAdminUsersGetQueryKey,
  listAdminUsersAdminUsersGet,
  useBanAdminUserAdminUsersUserIdBanPost,
  useDeleteAdminUserAdminUsersUserIdDelete,
  useForceVerifyAdminUserAdminUsersUserIdForceVerifyPost,
  useReinstateAdminUserAdminUsersUserIdReinstatePost,
  useSuspendAdminUserAdminUsersUserIdSuspendPost,
  UserStatus,
} from "@repo/api-client";
import type { AdminUserOut, ListAdminUsersAdminUsersGetParams } from "@repo/api-client";
import { unwrap, useAuth } from "@repo/web-shared";
import { Banner, Button } from "../../../components/form";
import { ACTION_META, describeApiError } from "../../../components/users/actionMeta";
import type { UserAction } from "../../../components/users/actionMeta";
import { ConfirmActionDialog } from "../../../components/users/ConfirmActionDialog";
import type { ConfirmActionTarget } from "../../../components/users/ConfirmActionDialog";
import { RolesDialog } from "../../../components/users/RolesDialog";

const PAGE_SIZE = 20;
/** Debounce delay between the last keystroke in the search box and the
 *  `?q=` request actually firing — avoids a request per keystroke. */
const SEARCH_DEBOUNCE_MS = 300;

const STATUS_OPTIONS: ReadonlyArray<{ value: "all" | UserStatus; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: UserStatus.active, label: "Active" },
  { value: UserStatus.suspended, label: "Suspended" },
  { value: UserStatus.banned, label: "Banned" },
];

/**
 * The user-management screen (Stage 13b) — list/search/paginate every
 * account via `GET /admin/users` and drive the per-user admin actions
 * (suspend/ban/reinstate/force-verify/edit roles/delete) added by the
 * merged 13b backend. Admin-gated purely by inheriting
 * `app/(app)/layout.tsx`'s whole-app `<ProtectedGate><AdminGate>` — no
 * per-page gate needed here (see that layout's docstring).
 *
 * Self-protection note: every mutating endpoint here 409s server-side if the
 * acting admin targets their own account in a way that would lock them out
 * (suspend/ban/delete self, or drop their own "admin" role — see
 * `app/api/routers/admin.py`'s `_ensure_not_self`). This page does NOT try
 * to pre-empt that client-side (no disabled buttons on "your own" row) —
 * the "(you)" tag next to the acting admin's own email is the only hint,
 * and attempting one of those actions on yourself surfaces the server's own
 * 409 message in the confirm dialog, same as any other conflict. Mirrors
 * this app's broader "the server is the real gate" posture (see the
 * dashboard's `/admin/ping` 403 handling).
 */
export default function UsersPage(): ReactNode {
  const { principal } = useAuth();
  const queryClient = useQueryClient();

  // --- search / filter / pagination state -----------------------------
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | UserStatus>("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const handle = setTimeout(() => setQ(qInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [qInput]);

  // Reset to page 1 whenever the search term or status filter actually
  // changes — but not on first mount (that would be a redundant no-op
  // setPage(1) before the very first fetch).
  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    setPage(1);
  }, [q, status]);

  const params: ListAdminUsersAdminUsersGetParams = {
    q: q.length > 0 ? q : undefined,
    status: status === "all" ? undefined : status,
    page,
    size: PAGE_SIZE,
  };

  // Same "wrap the generated call in unwrap() inside a plain useQuery" idiom
  // as the dashboard's `/admin/ping` check (`app/(app)/dashboard/page.tsx`)
  // rather than the generated `useListAdminUsersAdminUsersGet` hook directly
  // — that hook's `queryFn` resolves a documented non-2xx as SUCCESS (orval's
  // fetch mode never throws, see `unwrap`'s own docstring), which would
  // leave `isError`/`error` unusable for the 401/403/422 handling this page
  // needs. `getListAdminUsersAdminUsersGetQueryKey` (generated) still keys
  // the query, so mutation success handlers below can invalidate it by
  // prefix without hard-coding the `/admin/users` string.
  const listQuery = useQuery({
    queryKey: getListAdminUsersAdminUsersGetQueryKey(params),
    queryFn: async ({ signal }) => unwrap(await listAdminUsersAdminUsersGet(params, { signal })),
    placeholderData: keepPreviousData,
  });

  const users = listQuery.data?.items ?? [];
  const totalPages = listQuery.data ? Math.max(listQuery.data.pages, 1) : 1;

  const invalidateUsers = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getListAdminUsersAdminUsersGetQueryKey() });

  // --- per-row confirm-and-go actions (suspend/ban/reinstate/force-verify/
  // delete) — one dialog, one mutation hook per action, dispatched by
  // `confirmTarget.action`. See `ConfirmActionDialog`/`ACTION_META`. ------
  const suspendMutation = useSuspendAdminUserAdminUsersUserIdSuspendPost();
  const banMutation = useBanAdminUserAdminUsersUserIdBanPost();
  const reinstateMutation = useReinstateAdminUserAdminUsersUserIdReinstatePost();
  const forceVerifyMutation = useForceVerifyAdminUserAdminUsersUserIdForceVerifyPost();
  const deleteMutation = useDeleteAdminUserAdminUsersUserIdDelete();

  const [confirmTarget, setConfirmTarget] = useState<ConfirmActionTarget | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const openConfirm = (user: AdminUserOut, action: UserAction): void => {
    setActionError(null);
    setConfirmTarget({ user, action });
  };

  const closeConfirm = (): void => {
    if (actionPending) return;
    setConfirmTarget(null);
    setActionError(null);
  };

  const handleConfirm = async (): Promise<void> => {
    if (!confirmTarget) return;
    const { user, action } = confirmTarget;
    setActionPending(true);
    setActionError(null);
    try {
      // Each of these resolves `{ data, status, headers }` even on a
      // documented non-2xx (409/404/422/...) — `unwrap` is what turns that
      // into a thrown `ApiError` so the catch block below (and thus the
      // dialog's error banner) actually fires for a conflict.
      switch (action) {
        case "suspend":
          unwrap(await suspendMutation.mutateAsync({ userId: user.id }));
          break;
        case "ban":
          unwrap(await banMutation.mutateAsync({ userId: user.id }));
          break;
        case "reinstate":
          unwrap(await reinstateMutation.mutateAsync({ userId: user.id }));
          break;
        case "force-verify":
          unwrap(await forceVerifyMutation.mutateAsync({ userId: user.id }));
          break;
        case "delete":
          unwrap(await deleteMutation.mutateAsync({ userId: user.id }));
          break;
      }
      await invalidateUsers();
      setConfirmTarget(null);
    } catch (err) {
      // 409 (invalid transition, or self-protection) and any other failure
      // both land here — `ConfirmActionDialog` reads `describeApiError` to
      // show the server's own message, and the dialog stays open so the
      // admin can see it (no crash, no silent no-op).
      setActionError(err);
    } finally {
      setActionPending(false);
    }
  };

  // --- roles dialog ------------------------------------------------------
  const [rolesTarget, setRolesTarget] = useState<AdminUserOut | null>(null);
  const closeRoles = (): void => setRolesTarget(null);
  const handleRolesSuccess = (): void => {
    void invalidateUsers();
    setRolesTarget(null);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Users</h1>
        <p className="mt-1 text-muted">Search, filter, and manage user accounts.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="user-search" className="text-sm font-medium text-text">
            Search
          </label>
          <input
            id="user-search"
            type="search"
            value={qInput}
            onChange={(event) => setQInput(event.target.value)}
            placeholder="Search by email"
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="user-status" className="text-sm font-medium text-text">
            Status
          </label>
          <select
            id="user-status"
            value={status}
            onChange={(event) => setStatus(event.target.value as "all" | UserStatus)}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {listQuery.isError && <Banner tone="error">{describeApiError(listQuery.error)}</Banner>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-border bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Roles</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Verified</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {listQuery.isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  Loading users…
                </td>
              </tr>
            )}
            {!listQuery.isPending && !listQuery.isError && users.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  No users match your search.
                </td>
              </tr>
            )}
            {users.map((user) => (
              <tr key={user.id}>
                <td className="px-4 py-3 text-text">
                  {user.email}
                  {principal?.id === user.id && (
                    <span className="ml-2 text-xs text-muted">(you)</span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted">
                  {user.roles.length > 0 ? user.roles.join(", ") : "—"}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={user.status} />
                </td>
                <td className="px-4 py-3 text-muted">{user.email_verified ? "Yes" : "No"}</td>
                <td className="px-4 py-3 text-muted">{formatDate(user.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {availableActions(user).map((action) => (
                      <Button
                        key={action}
                        size="sm"
                        variant={ACTION_META[action].destructive ? "danger" : "secondary"}
                        onClick={() => openConfirm(user, action)}
                      >
                        {ACTION_META[action].shortLabel}
                      </Button>
                    ))}
                    <Button size="sm" variant="secondary" onClick={() => setRolesTarget(user)}>
                      Edit roles
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
        <span>
          {listQuery.data
            ? `${listQuery.data.total} user${listQuery.data.total === 1 ? "" : "s"}`
            : ""}
        </span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            Previous
          </Button>
          <span>
            Page {page} of {totalPages}
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={!listQuery.data || page >= listQuery.data.pages}
            onClick={() => setPage((current) => current + 1)}
          >
            Next
          </Button>
        </div>
      </div>

      <ConfirmActionDialog
        target={confirmTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={() => void handleConfirm()}
        onClose={closeConfirm}
      />
      <RolesDialog user={rolesTarget} onClose={closeRoles} onSuccess={handleRolesSuccess} />
    </div>
  );
}

/** Which confirm-and-go actions are valid to OFFER for `user`'s current
 *  status — mirrors the backend's exact from-state rules (see
 *  `ACTION_META`'s docstring). Delete has no status precondition; force-
 *  verify is hidden once already verified (nothing left to do). The server
 *  remains the authoritative check either way — this only avoids offering a
 *  button guaranteed to 409. */
const availableActions = (user: AdminUserOut): UserAction[] => {
  const actions: UserAction[] = [];
  if (user.status === UserStatus.active) actions.push("suspend");
  if (user.status === UserStatus.active || user.status === UserStatus.suspended) {
    actions.push("ban");
  }
  if (user.status === UserStatus.suspended || user.status === UserStatus.banned) {
    actions.push("reinstate");
  }
  if (!user.email_verified) actions.push("force-verify");
  actions.push("delete");
  return actions;
};

const STATUS_BADGE_CLASS: Record<UserStatus, string> = {
  [UserStatus.active]: "border-success text-success",
  [UserStatus.suspended]: "border-border text-muted",
  [UserStatus.banned]: "border-danger text-danger",
};

const StatusBadge = ({ status }: { status: UserStatus }): ReactNode => (
  <span
    className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${STATUS_BADGE_CLASS[status]}`}
  >
    {status}
  </span>
);

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
};
