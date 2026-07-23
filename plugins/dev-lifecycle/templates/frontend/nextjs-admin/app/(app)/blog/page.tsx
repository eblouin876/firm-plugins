"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BlogPostStatus,
  getListAdminBlogPostsAdminBlogPostsGetQueryKey,
  listAdminBlogPostsAdminBlogPostsGet,
  useDeleteAdminBlogPostAdminBlogPostsPostIdDelete,
  usePublishAdminBlogPostAdminBlogPostsPostIdPublishPost,
  useUnpublishAdminBlogPostAdminBlogPostsPostIdUnpublishPost,
} from "@repo/api-client";
import type { BlogPostSummaryOut, ListAdminBlogPostsAdminBlogPostsGetParams } from "@repo/api-client";
import { unwrap } from "@repo/web-shared";
import { Banner, Button } from "../../../components/form";
import {
  ConfirmPostActionDialog,
  POST_ACTION_META,
} from "../../../components/blog/ConfirmPostActionDialog";
import type { BlogPostAction, ConfirmPostActionTarget } from "../../../components/blog/ConfirmPostActionDialog";
import { describeBlogError } from "../../../components/blog/blogErrors";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: ReadonlyArray<{ value: "all" | BlogPostStatus; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: BlogPostStatus.draft, label: "Draft" },
  { value: BlogPostStatus.published, label: "Published" },
];

/**
 * The blog admin screen (Stage 13d) — list/filter/paginate every post via
 * `GET /admin/blog/posts` and drive the per-post publish/unpublish/delete
 * actions against the merged 13d backend. Admin-gated purely by inheriting
 * `app/(app)/layout.tsx`'s whole-app `<ProtectedGate><AdminGate>` — same
 * posture as `app/(app)/users/page.tsx`, which this page's structure
 * mirrors closely (raw-call + `unwrap` for the list query, a shared
 * confirm-and-go dialog for the state-changing actions, invalidate-on-
 * success).
 */
export default function BlogPage(): ReactNode {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [status, setStatus] = useState<"all" | BlogPostStatus>("all");
  const [page, setPage] = useState(1);

  const params: ListAdminBlogPostsAdminBlogPostsGetParams = {
    status: status === "all" ? undefined : status,
    page,
    size: PAGE_SIZE,
  };

  // Same "raw call + useQuery + unwrap" idiom as `app/(app)/users/page.tsx`'s
  // `listQuery` — the generated `useListAdminBlogPostsAdminBlogPostsGet`
  // hook's own `queryFn` resolves a documented non-2xx (401/403/422) as
  // SUCCESS (orval's fetch mode never throws), which would leave
  // `isError`/`error` unusable here.
  const listQuery = useQuery({
    queryKey: getListAdminBlogPostsAdminBlogPostsGetQueryKey(params),
    queryFn: async ({ signal }) => unwrap(await listAdminBlogPostsAdminBlogPostsGet(params, { signal })),
    placeholderData: keepPreviousData,
  });

  const posts = listQuery.data?.items ?? [];
  const totalPages = listQuery.data ? Math.max(listQuery.data.pages, 1) : 1;

  const invalidatePosts = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getListAdminBlogPostsAdminBlogPostsGetQueryKey() });

  const publishMutation = usePublishAdminBlogPostAdminBlogPostsPostIdPublishPost();
  const unpublishMutation = useUnpublishAdminBlogPostAdminBlogPostsPostIdUnpublishPost();
  const deleteMutation = useDeleteAdminBlogPostAdminBlogPostsPostIdDelete();

  const [confirmTarget, setConfirmTarget] = useState<ConfirmPostActionTarget | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const openConfirm = (post: BlogPostSummaryOut, action: BlogPostAction): void => {
    setActionError(null);
    setConfirmTarget({ post, action });
  };

  const closeConfirm = (): void => {
    if (actionPending) return;
    setConfirmTarget(null);
    setActionError(null);
  };

  const handleConfirm = async (): Promise<void> => {
    if (!confirmTarget) return;
    const { post, action } = confirmTarget;
    setActionPending(true);
    setActionError(null);
    try {
      // Each mutation's `mutateAsync` resolves the same `{ data, status,
      // headers }` shape as the raw generated call (its `mutationFn` just
      // forwards to it) — `unwrap` is what turns a 404/409/422 into a thrown
      // `ApiError` so the catch block below fires instead of silently
      // treating the conflict as success.
      switch (action) {
        case "publish":
          unwrap(await publishMutation.mutateAsync({ postId: post.id }));
          break;
        case "unpublish":
          unwrap(await unpublishMutation.mutateAsync({ postId: post.id }));
          break;
        case "delete":
          unwrap(await deleteMutation.mutateAsync({ postId: post.id }));
          break;
      }
      await invalidatePosts();
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
          <h1 className="text-2xl font-semibold">Blog</h1>
          <p className="mt-1 text-muted">Draft, publish, and manage blog posts.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => router.push("/blog/comments")}>
            Comments
          </Button>
          <Button onClick={() => router.push("/blog/new")}>New post</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="post-status" className="text-sm font-medium text-text">
            Status
          </label>
          <select
            id="post-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as "all" | BlogPostStatus);
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
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-border bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Slug</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Published</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {listQuery.isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  Loading posts…
                </td>
              </tr>
            )}
            {!listQuery.isPending && !listQuery.isError && posts.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  No posts match this filter.
                </td>
              </tr>
            )}
            {posts.map((post) => (
              <tr key={post.id}>
                <td className="px-4 py-3 text-text">{post.title}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted">{post.slug}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={post.status} />
                </td>
                <td className="px-4 py-3 text-muted">
                  {post.published_at ? formatDate(post.published_at) : "—"}
                </td>
                <td className="px-4 py-3 text-muted">{formatDate(post.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" variant="secondary" onClick={() => router.push(`/blog/${post.id}/edit`)}>
                      Edit
                    </Button>
                    {availablePostActions(post).map((action) => (
                      <Button
                        key={action}
                        size="sm"
                        variant={POST_ACTION_META[action].destructive ? "danger" : "secondary"}
                        onClick={() => openConfirm(post, action)}
                      >
                        {POST_ACTION_META[action].shortLabel}
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
            ? `${listQuery.data.total} post${listQuery.data.total === 1 ? "" : "s"}`
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

      <ConfirmPostActionDialog
        target={confirmTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={() => void handleConfirm()}
        onClose={closeConfirm}
      />
    </div>
  );
}

/** Which confirm-and-go actions are valid to OFFER for `post`'s current
 *  status — mirrors the backend's exact from-state rules (see
 *  `POST_ACTION_META`'s docstring in `ConfirmPostActionDialog.tsx`). Delete
 *  has no status precondition. The server remains the authoritative check
 *  either way — this only avoids offering a button guaranteed to 409. */
const availablePostActions = (post: BlogPostSummaryOut): BlogPostAction[] => {
  const actions: BlogPostAction[] = [];
  if (post.status === BlogPostStatus.draft) actions.push("publish");
  if (post.status === BlogPostStatus.published) actions.push("unpublish");
  actions.push("delete");
  return actions;
};

const STATUS_BADGE_CLASS: Record<BlogPostStatus, string> = {
  [BlogPostStatus.draft]: "border-border text-muted",
  [BlogPostStatus.published]: "border-success text-success",
};

const StatusBadge = ({ status }: { status: BlogPostStatus }): ReactNode => (
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
