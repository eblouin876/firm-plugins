"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CommentStatus,
  getListAdminBlogCommentsAdminBlogCommentsGetQueryKey,
  listAdminBlogCommentsAdminBlogCommentsGet,
  useDeleteAdminBlogCommentAdminBlogCommentsCommentIdDelete,
  useHideAdminBlogCommentAdminBlogCommentsCommentIdHidePost,
} from "@repo/api-client";
import type { CommentOut, ListAdminBlogCommentsAdminBlogCommentsGetParams } from "@repo/api-client";
import { unwrap } from "@repo/web-shared";
import { Banner, Button } from "../../../../components/form";
import {
  COMMENT_ACTION_META,
  ConfirmCommentActionDialog,
} from "../../../../components/blog/ConfirmCommentActionDialog";
import type {
  CommentAction,
  ConfirmCommentActionTarget,
} from "../../../../components/blog/ConfirmCommentActionDialog";
import { describeBlogError } from "../../../../components/blog/blogErrors";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: ReadonlyArray<{ value: "all" | CommentStatus; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: CommentStatus.visible, label: "Visible" },
  { value: CommentStatus.pending, label: "Pending" },
  { value: CommentStatus.hidden, label: "Hidden" },
];

/**
 * A lightweight blog-comment view — list/filter (`GET /admin/blog/comments`)
 * plus Hide/Delete, against the merged 13d backend's comment-status
 * endpoints. Deliberately NOT the Stage 13c Flag/Report moderation queue
 * (that stage owns the flagging/moderation-decision workflow this repo's
 * planning docs describe); this is only the blog-scoped "hide a comment
 * from a post" action the blog endpoints themselves expose. Structured the
 * same way as `app/(app)/blog/page.tsx` (raw-call + `unwrap` list query,
 * one shared confirm dialog, invalidate-on-success).
 */
export default function BlogCommentsPage(): ReactNode {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [status, setStatus] = useState<"all" | CommentStatus>("all");
  const [page, setPage] = useState(1);

  const params: ListAdminBlogCommentsAdminBlogCommentsGetParams = {
    status: status === "all" ? undefined : status,
    page,
    size: PAGE_SIZE,
  };

  const listQuery = useQuery({
    queryKey: getListAdminBlogCommentsAdminBlogCommentsGetQueryKey(params),
    queryFn: async ({ signal }) =>
      unwrap(await listAdminBlogCommentsAdminBlogCommentsGet(params, { signal })),
    placeholderData: keepPreviousData,
  });

  const comments = listQuery.data?.items ?? [];
  const totalPages = listQuery.data ? Math.max(listQuery.data.pages, 1) : 1;

  const invalidateComments = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getListAdminBlogCommentsAdminBlogCommentsGetQueryKey() });

  const hideMutation = useHideAdminBlogCommentAdminBlogCommentsCommentIdHidePost();
  const deleteMutation = useDeleteAdminBlogCommentAdminBlogCommentsCommentIdDelete();

  const [confirmTarget, setConfirmTarget] = useState<ConfirmCommentActionTarget | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const openConfirm = (comment: CommentOut, action: CommentAction): void => {
    setActionError(null);
    setConfirmTarget({ comment, action });
  };
  const closeConfirm = (): void => {
    if (actionPending) return;
    setConfirmTarget(null);
    setActionError(null);
  };

  const handleConfirm = async (): Promise<void> => {
    if (!confirmTarget) return;
    const { comment, action } = confirmTarget;
    setActionPending(true);
    setActionError(null);
    try {
      switch (action) {
        case "hide":
          unwrap(await hideMutation.mutateAsync({ commentId: comment.id }));
          break;
        case "delete":
          unwrap(await deleteMutation.mutateAsync({ commentId: comment.id }));
          break;
      }
      await invalidateComments();
      setConfirmTarget(null);
    } catch (err) {
      setActionError(err);
    } finally {
      setActionPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Blog comments</h1>
          <p className="mt-1 text-muted">Hide or delete comments left on blog posts.</p>
        </div>
        <Button variant="secondary" onClick={() => router.push("/blog")}>
          Back to posts
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="comment-status" className="text-sm font-medium text-text">
            Status
          </label>
          <select
            id="comment-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as "all" | CommentStatus);
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
      </div>

      {listQuery.isError && <Banner tone="error">{describeBlogError(listQuery.error)}</Banner>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-border bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Comment</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {listQuery.isPending && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-muted">
                  Loading comments…
                </td>
              </tr>
            )}
            {!listQuery.isPending && !listQuery.isError && comments.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-muted">
                  No comments match this filter.
                </td>
              </tr>
            )}
            {comments.map((comment) => (
              <tr key={comment.id}>
                <td className="max-w-md truncate px-4 py-3 text-text">{comment.body}</td>
                <td className="px-4 py-3 capitalize text-muted">{comment.status}</td>
                <td className="px-4 py-3 text-muted">{formatDate(comment.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {availableCommentActions(comment).map((action) => (
                      <Button
                        key={action}
                        size="sm"
                        variant={COMMENT_ACTION_META[action].destructive ? "danger" : "secondary"}
                        onClick={() => openConfirm(comment, action)}
                      >
                        {COMMENT_ACTION_META[action].shortLabel}
                      </Button>
                    ))}
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
            ? `${listQuery.data.total} comment${listQuery.data.total === 1 ? "" : "s"}`
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

      <ConfirmCommentActionDialog
        target={confirmTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={() => void handleConfirm()}
        onClose={closeConfirm}
      />
    </div>
  );
}

const availableCommentActions = (comment: CommentOut): CommentAction[] => {
  const actions: CommentAction[] = [];
  if (comment.status === CommentStatus.visible || comment.status === CommentStatus.pending) {
    actions.push("hide");
  }
  actions.push("delete");
  return actions;
};

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
};
