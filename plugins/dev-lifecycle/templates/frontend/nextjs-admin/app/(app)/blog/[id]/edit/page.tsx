"use client";

import type { ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  BlogPostStatus,
  getAdminBlogPostAdminBlogPostsPostIdGet,
  getGetAdminBlogPostAdminBlogPostsPostIdGetQueryKey,
  getListAdminBlogPostsAdminBlogPostsGetQueryKey,
  useDeleteAdminBlogPostAdminBlogPostsPostIdDelete,
  usePublishAdminBlogPostAdminBlogPostsPostIdPublishPost,
  useUnpublishAdminBlogPostAdminBlogPostsPostIdUnpublishPost,
  useUpdateAdminBlogPostAdminBlogPostsPostIdPatch,
} from "@repo/api-client";
import type { BlogPostOut, BlogPostUpdate } from "@repo/api-client";
import { unwrap } from "@repo/web-shared";
import { Banner, Button } from "../../../../../components/form";
import { BlogPostForm } from "../../../../../components/blog/BlogPostForm";
import type { BlogPostSubmitPayload } from "../../../../../components/blog/BlogPostForm";
import {
  ConfirmPostActionDialog,
  POST_ACTION_META,
} from "../../../../../components/blog/ConfirmPostActionDialog";
import type { BlogPostAction, ConfirmPostActionTarget } from "../../../../../components/blog/ConfirmPostActionDialog";
import { describeBlogError } from "../../../../../components/blog/blogErrors";

/**
 * Load and edit one blog post — `GET /admin/blog/posts/{id}` seeds the
 * form, `PATCH` saves it, and the same Publish/Unpublish/Delete actions the
 * list page offers are available here too (an admin editing a draft
 * shouldn't have to leave the screen to publish it). Split into an outer
 * data-fetching shell (`EditBlogPostPage`) and an inner `EditPostForm`
 * mounted with `key={post.id}` once the post has loaded — the same
 * remount-for-fresh-defaults trick `components/users/RolesDialog.tsx` uses,
 * needed here because `useZodForm`'s `defaultValues` and `BlogEditor`'s
 * `initialContent` are both only correct once the fetched post is in hand.
 */
export default function EditBlogPostPage(): ReactNode {
  const { id } = useParams<{ id: string }>();
  const postId = typeof id === "string" ? id : "";

  const postQuery = useQuery({
    queryKey: getGetAdminBlogPostAdminBlogPostsPostIdGetQueryKey(postId),
    queryFn: async ({ signal }) => unwrap(await getAdminBlogPostAdminBlogPostsPostIdGet(postId, { signal })),
    enabled: postId.length > 0,
  });

  if (postQuery.isPending) {
    return <p className="text-muted">Loading post…</p>;
  }

  if (postQuery.isError) {
    return <Banner tone="error">{describeBlogError(postQuery.error)}</Banner>;
  }

  return <EditPostForm key={postQuery.data.id} post={postQuery.data} />;
}

const EditPostForm = ({ post }: { post: BlogPostOut }): ReactNode => {
  const router = useRouter();
  const queryClient = useQueryClient();

  const updateMutation = useUpdateAdminBlogPostAdminBlogPostsPostIdPatch();
  const publishMutation = usePublishAdminBlogPostAdminBlogPostsPostIdPublishPost();
  const unpublishMutation = useUnpublishAdminBlogPostAdminBlogPostsPostIdUnpublishPost();
  const deleteMutation = useDeleteAdminBlogPostAdminBlogPostsPostIdDelete();

  const invalidatePost = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getGetAdminBlogPostAdminBlogPostsPostIdGetQueryKey(post.id) });
  const invalidateList = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: getListAdminBlogPostsAdminBlogPostsGetQueryKey() });

  const handleSave = async (values: BlogPostSubmitPayload): Promise<void> => {
    const payload: BlogPostUpdate = {
      title: values.title,
      slug: values.slug,
      body_json: values.body_json,
      body_html: values.body_html,
    };
    unwrap(await updateMutation.mutateAsync({ postId: post.id, data: payload }));
    await Promise.all([invalidatePost(), invalidateList()]);
  };

  const [confirmTarget, setConfirmTarget] = useState<ConfirmPostActionTarget | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const openConfirm = (action: BlogPostAction): void => {
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
    setActionPending(true);
    setActionError(null);
    try {
      switch (confirmTarget.action) {
        case "publish":
          unwrap(await publishMutation.mutateAsync({ postId: post.id }));
          await Promise.all([invalidatePost(), invalidateList()]);
          setConfirmTarget(null);
          break;
        case "unpublish":
          unwrap(await unpublishMutation.mutateAsync({ postId: post.id }));
          await Promise.all([invalidatePost(), invalidateList()]);
          setConfirmTarget(null);
          break;
        case "delete":
          unwrap(await deleteMutation.mutateAsync({ postId: post.id }));
          await invalidateList();
          router.push("/blog");
          break;
      }
    } catch (err) {
      setActionError(err);
    } finally {
      setActionPending(false);
    }
  };

  const availableActions: BlogPostAction[] =
    post.status === BlogPostStatus.draft ? ["publish", "delete"] : ["unpublish", "delete"];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Edit post</h1>
          <p className="mt-1 text-muted">
            Status:{" "}
            <span className="font-medium capitalize text-text">{post.status}</span>
            {post.published_at && <> · Published {formatDate(post.published_at)}</>}
          </p>
        </div>
      </div>

      <BlogPostForm
        defaultValues={{ title: post.title, slug: post.slug }}
        initialBody={post.body_json}
        submitLabel="Save changes"
        onSubmit={handleSave}
        extraActions={
          <>
            {availableActions.map((action) => (
              <Button
                key={action}
                variant={POST_ACTION_META[action].destructive ? "danger" : "secondary"}
                onClick={() => openConfirm(action)}
              >
                {POST_ACTION_META[action].shortLabel}
              </Button>
            ))}
          </>
        }
      />

      <ConfirmPostActionDialog
        target={confirmTarget}
        pending={actionPending}
        error={actionError}
        onConfirm={() => void handleConfirm()}
        onClose={closeConfirm}
      />
    </div>
  );
};

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
};
