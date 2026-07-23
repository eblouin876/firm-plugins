"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FlagStatus,
  FlagTargetType,
  getListAdminFlagsAdminFlagsGetQueryKey,
  listAdminFlagsAdminFlagsGet,
  useDismissAdminFlagAdminFlagsFlagIdDismissPost,
  useResolveAdminFlagAdminFlagsFlagIdResolvePost,
} from "@repo/api-client";
import type { FlagOut, ListAdminFlagsAdminFlagsGetParams } from "@repo/api-client";
import { unwrap } from "@repo/web-shared";
import { Banner, Button } from "../../../components/form";
import { DismissFlagDialog } from "../../../components/moderation/DismissFlagDialog";
import type { DismissFlagPayload, DismissFlagTarget } from "../../../components/moderation/DismissFlagDialog";
import { describeModerationError } from "../../../components/moderation/moderationErrors";
import { ResolveFlagDialog } from "../../../components/moderation/ResolveFlagDialog";
import type { ResolveFlagPayload, ResolveFlagTarget } from "../../../components/moderation/ResolveFlagDialog";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: ReadonlyArray<{ value: "all" | FlagStatus; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: FlagStatus.open, label: "Open" },
  { value: FlagStatus.resolved, label: "Resolved" },
  { value: FlagStatus.dismissed, label: "Dismissed" },
];

const TARGET_TYPE_OPTIONS: ReadonlyArray<{ value: "all" | FlagTargetType; label: string }> = [
  { value: "all", label: "All targets" },
  { value: FlagTargetType.blog_post, label: "Blog posts" },
  { value: FlagTargetType.comment, label: "Comments" },
  { value: FlagTargetType.user, label: "Users" },
];

/**
 * The Stage 13c moderation queue — list/filter/paginate reports via
 * `GET /admin/flags` (`?status=&target_type=&page=&size=`) and drive the
 * per-flag Resolve/Dismiss actions added by the merged 13c backend
 * (`app/api/routers/moderation.py`). Admin-gated purely by inheriting
 * `app/(app)/layout.tsx`'s whole-app `<ProtectedGate><AdminGate>` — no
 * per-page gate needed here, same posture as `app/(app)/users/page.tsx`.
 *
 * Structured the same way as that page and `app/(app)/blog/page.tsx`: a
 * raw-call + `unwrap()` list query (NOT the generated `use*` hook's own
 * result — orval's fetch mode resolves a non-2xx as success, so `unwrap()`
 * is what turns it into a throwable `ApiError`), one dialog per action
 * (`ResolveFlagDialog`/`DismissFlagDialog`), and a query-key-helper-driven
 * invalidation on success so a row reflects its new status without a full
 * page reload.
 *
 * Defaults to the `open` filter — the queue's working view — rather than
 * `all`, so a fresh visit shows exactly what still needs a decision.
 *
 * Error handling: a 409 (the flag was already resolved/dismissed by another
 * admin between page-load and click, or the backend's ban-author self-
 * protection guard — `_ensure_not_self` in `app/api/routers/moderation.py`)
 * and a 422 (e.g. `hide_content`/`delete_content` posted against a `user`
 * target — `ResolveFlagDialog`'s action selector already avoids offering
 * this, the 422 handling here is the backstop) both surface the server's
 * own message in the open dialog via `describeModerationError`, and leave
 * the dialog open rather than crashing or silently closing.
 */
export default function ModerationPage(): ReactNode {
  const queryClient = useQueryClient();

  const [status, setStatus] = useState<"all" | FlagStatus>(FlagStatus.open);
  const [targetType, setTargetType] = useState<"all" | FlagTargetType>("all");
  const [page, setPage] = useState(1);

  const params: ListAdminFlagsAdminFlagsGetParams = {
    status: status === "all" ? undefined : status,
    target_type: targetType === "all" ? undefined : targetType,
    page,
    size: PAGE_SIZE,
  };

  const listQuery = useQuery({
    queryKey: getListAdminFlagsAdminFlagsGetQueryKey(params),
    queryFn: async ({ signal }) => unwrap(await listAdminFlagsAdminFlagsGet(params, { signal })),
    placeholderData: keepPreviousData,
  });

  const flags = listQuery.data?.items ?? [];
  const totalPages = listQuery.data ? Math.max(listQuery.data.pages, 1) : 1;

  const invalidateFlags = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getListAdminFlagsAdminFlagsGetQueryKey() });

  // --- resolve / dismiss actions -----------------------------------------
  const resolveMutation = useResolveAdminFlagAdminFlagsFlagIdResolvePost();
  const dismissMutation = useDismissAdminFlagAdminFlagsFlagIdDismissPost();

  const [resolveTarget, setResolveTarget] = useState<ResolveFlagTarget | null>(null);
  const [dismissTarget, setDismissTarget] = useState<DismissFlagTarget | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const openResolve = (flag: FlagOut): void => {
    setActionError(null);
    setResolveTarget({ flag });
  };
  const openDismiss = (flag: FlagOut): void => {
    setActionError(null);
    setDismissTarget({ flag });
  };
  const closeDialogs = (): void => {
    if (actionPending) return;
    setResolveTarget(null);
    setDismissTarget(null);
    setActionError(null);
  };

  const handleResolveConfirm = async (payload: ResolveFlagPayload): Promise<void> => {
    if (!resolveTarget) return;
    setActionPending(true);
    setActionError(null);
    try {
      // `unwrap()` — not the mutation hook's own `.data`/`.error` — is what
      // turns a documented non-2xx (409 already-resolved / self-protection,
      // 422 invalid action for this target_type) into a thrown `ApiError`
      // this catch block can surface.
      unwrap(
        await resolveMutation.mutateAsync({
          flagId: resolveTarget.flag.id,
          data: { action: payload.action, note: payload.note },
        }),
      );
      await invalidateFlags();
      setResolveTarget(null);
    } catch (err) {
      setActionError(err);
    } finally {
      setActionPending(false);
    }
  };

  const handleDismissConfirm = async (payload: DismissFlagPayload): Promise<void> => {
    if (!dismissTarget) return;
    setActionPending(true);
    setActionError(null);
    try {
      unwrap(
        await dismissMutation.mutateAsync({
          flagId: dismissTarget.flag.id,
          data: { note: payload.note },
        }),
      );
      await invalidateFlags();
      setDismissTarget(null);
    } catch (err) {
      setActionError(err);
    } finally {
      setActionPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Moderation</h1>
        <p className="mt-1 text-muted">Review reported content and accounts, and resolve or dismiss the report.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="flag-status" className="text-sm font-medium text-text">
            Status
          </label>
          <select
            id="flag-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as "all" | FlagStatus);
              setPage(1);
            }}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="flag-target-type" className="text-sm font-medium text-text">
            Target
          </label>
          <select
            id="flag-target-type"
            value={targetType}
            onChange={(event) => {
              setTargetType(event.target.value as "all" | FlagTargetType);
              setPage(1);
            }}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {TARGET_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {listQuery.isError && <Banner tone="error">{describeModerationError(listQuery.error)}</Banner>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-border bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Target</th>
              <th className="px-4 py-3 font-medium">Reason</th>
              <th className="px-4 py-3 font-medium">Reporter</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {listQuery.isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  Loading flags…
                </td>
              </tr>
            )}
            {!listQuery.isPending && !listQuery.isError && flags.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  No flags match this filter.
                </td>
              </tr>
            )}
            {flags.map((flag) => (
              <tr key={flag.id}>
                <td className="px-4 py-3 text-text">
                  <span className="capitalize">{flag.target_type.replace("_", " ")}</span>{" "}
                  <span className="font-mono text-xs text-muted">{flag.target_id}</span>
                </td>
                <td className="max-w-xs truncate px-4 py-3 text-text" title={flag.reason}>
                  {flag.reason}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-muted">{flag.reporter_id ?? "System"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={flag.status} />
                </td>
                <td className="px-4 py-3 text-muted">{formatDate(flag.created_at)}</td>
                <td className="px-4 py-3">
                  {flag.status === FlagStatus.open ? (
                    <div className="flex flex-wrap gap-1.5">
                      <Button size="sm" variant="secondary" onClick={() => openResolve(flag)}>
                        Resolve
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => openDismiss(flag)}>
                        Dismiss
                      </Button>
                    </div>
                  ) : (
                    <div className="text-xs text-muted">
                      <span className="capitalize">{flag.status}</span>
                      {flag.resolved_at && <> · {formatDate(flag.resolved_at)}</>}
                      {flag.resolved_by_id && (
                        <>
                          {" "}
                          by <span className="font-mono">{flag.resolved_by_id}</span>
                        </>
                      )}
                      {flag.resolution_note && <p className="mt-1 max-w-xs truncate">{flag.resolution_note}</p>}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
        <span>
          {listQuery.data
            ? `${listQuery.data.total} flag${listQuery.data.total === 1 ? "" : "s"}`
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

      <ResolveFlagDialog
        target={resolveTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={(payload) => void handleResolveConfirm(payload)}
        onClose={closeDialogs}
      />
      <DismissFlagDialog
        target={dismissTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={(payload) => void handleDismissConfirm(payload)}
        onClose={closeDialogs}
      />
    </div>
  );
}

const STATUS_BADGE_CLASS: Record<FlagStatus, string> = {
  [FlagStatus.open]: "border-danger text-danger",
  [FlagStatus.resolved]: "border-success text-success",
  [FlagStatus.dismissed]: "border-border text-muted",
};

const StatusBadge = ({ status }: { status: FlagStatus }): ReactNode => (
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
