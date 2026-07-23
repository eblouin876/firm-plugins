"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  getListAdminBlogPostsAdminBlogPostsGetQueryKey,
  useCreateAdminBlogPostAdminBlogPostsPost,
} from "@repo/api-client";
import type { BlogPostCreate } from "@repo/api-client";
import { unwrap } from "@repo/web-shared";
import { BlogPostForm } from "../../../../components/blog/BlogPostForm";
import type { BlogPostSubmitPayload } from "../../../../components/blog/BlogPostForm";

/**
 * Create a new blog post — `POST /admin/blog/posts` with both
 * `body_json`/`body_html` from the TipTap editor (`BlogPostForm` +
 * `BlogEditor`). `slug` is sent only when the admin actually typed one;
 * left blank, the server derives one from `title` and never 409s for that
 * derived case (an EXPLICITLY chosen, colliding slug does 409 — surfaced
 * via `BlogPostForm`'s `applyEnvelopeToForm`/banner handling, same idiom as
 * `components/users/RolesDialog.tsx`). On success, redirects straight to
 * the new post's edit screen (where Publish lives) rather than back to the
 * list.
 */
export default function NewBlogPostPage(): ReactNode {
  const router = useRouter();
  const queryClient = useQueryClient();
  const createMutation = useCreateAdminBlogPostAdminBlogPostsPost();

  const handleSubmit = async (values: BlogPostSubmitPayload): Promise<void> => {
    const payload: BlogPostCreate = {
      title: values.title,
      slug: values.slug,
      body_json: values.body_json,
      body_html: values.body_html,
    };
    // `unwrap` turns the merged 13d backend's 409 (duplicate explicit slug)
    // or 422 (invalid slug shape / oversize body) into a thrown `ApiError`
    // — `BlogPostForm`'s own catch block is what maps that onto the form.
    const post = unwrap(await createMutation.mutateAsync({ data: payload }));
    await queryClient.invalidateQueries({ queryKey: getListAdminBlogPostsAdminBlogPostsGetQueryKey() });
    router.push(`/blog/${post.id}/edit`);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">New post</h1>
        <p className="mt-1 text-muted">
          Drafts stay unpublished until you publish them from the edit screen.
        </p>
      </div>
      <BlogPostForm submitLabel="Create post" onSubmit={handleSubmit} />
    </div>
  );
}
