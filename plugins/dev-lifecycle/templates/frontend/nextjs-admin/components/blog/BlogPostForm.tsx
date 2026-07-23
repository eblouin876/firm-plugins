"use client";

import { useRef } from "react";
import type { ReactNode } from "react";
import { z } from "zod";
import { applyEnvelopeToForm, useZodForm } from "@repo/web-shared";
import { Banner, Button, TextInput } from "../form";
import { BlogEditor } from "../editor/BlogEditor";
import type { BlogEditorHandle } from "../editor/BlogEditor";
import { describeBlogError } from "./blogErrors";

// Slug shape mirrors the backend's own `Field(pattern=r"^[a-z0-9-]+$")` (see
// `BlogPostCreate`'s docstring, `templates/packages/api-client/src/
// generated/models/blogPostCreate.ts`) — client-side validation here is a
// UX nicety (catch an obviously-wrong slug before a round trip), NOT the
// authoritative check: an empty string is treated as "not supplied" (server
// derives one from the title), and any other value still goes through the
// server's own validation/uniqueness check regardless of what passes here.
const SLUG_PATTERN = /^[a-z0-9-]+$/;

const schema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Title is required.")
    .max(200, "Title must be 200 characters or fewer."),
  slug: z
    .string()
    .trim()
    .max(200, "Slug must be 200 characters or fewer.")
    .refine((value) => value.length === 0 || SLUG_PATTERN.test(value), {
      message: "Slug may only contain lowercase letters, numbers, and hyphens.",
    })
    .optional(),
});

export type BlogPostFormValues = z.infer<typeof schema>;

export interface BlogPostSubmitPayload {
  title: string;
  /** `undefined` when the slug field was left blank — the server derives
   *  one from `title` in that case; never sent as an explicit empty string. */
  slug: string | undefined;
  body_json: Record<string, unknown>;
  body_html: string;
}

interface BlogPostFormProps {
  defaultValues?: Partial<BlogPostFormValues>;
  /** Seeds the editor from the post's `body_json` — see `BlogEditor`'s own
   *  docstring on why never `body_html`. `undefined` starts a blank post. */
  initialBody?: Record<string, unknown>;
  submitLabel: string;
  onSubmit: (values: BlogPostSubmitPayload) => Promise<void>;
  /** Extra action buttons rendered next to Save — the edit page's
   *  Publish/Unpublish/Delete; the new-post page passes nothing. */
  extraActions?: ReactNode;
}

/**
 * The title/slug/body form shared by the "new post" and "edit post" pages —
 * only what differs (default values, the initial editor content, the submit
 * handler, and edit-only action buttons) is passed in as props. Title/slug
 * are plain `react-hook-form` fields (`useZodForm`); the body is NOT part of
 * the RHF form state — `BlogEditor` is imperative (a ref), so typing in the
 * editor never re-renders this form, and the body is only pulled via
 * `editorRef.current.getContent()` at submit time (see `BlogEditor`'s own
 * docstring on `getContent`).
 *
 * Error idiom mirrors `components/users/RolesDialog.tsx`: `onSubmit` is
 * expected to call the generated mutation hook + `unwrap()` and let a
 * non-2xx throw; a thrown `ApiError` lands here, where a 422
 * `validation_failed` maps onto the matching field (`title`/`slug`) via
 * `applyEnvelopeToForm`, and everything else (a 409 duplicate-slug conflict,
 * a network failure) falls back to a form-level banner via
 * `describeBlogError`.
 */
export const BlogPostForm = ({
  defaultValues,
  initialBody,
  submitLabel,
  onSubmit,
  extraActions,
}: BlogPostFormProps): ReactNode => {
  const editorRef = useRef<BlogEditorHandle>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { title: "", slug: "", ...defaultValues } });

  const submit = handleSubmit(async (values) => {
    const content = editorRef.current?.getContent() ?? {
      body_json: { type: "doc", content: [] },
      body_html: "<p></p>",
    };
    try {
      await onSubmit({
        title: values.title,
        slug: values.slug && values.slug.length > 0 ? values.slug : undefined,
        ...content,
      });
    } catch (err) {
      // 422 validation_failed (bad title/slug) lands on the matching field;
      // a 409 duplicate-slug conflict (or anything else) falls back to a
      // form-level banner with the server's own message.
      if (applyEnvelopeToForm(err, setError)) return;
      setError("root", { message: describeBlogError(err) });
    }
  });

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {errors.root?.message && <Banner tone="error">{errors.root.message}</Banner>}
      <TextInput label="Title" registration={register("title")} error={errors.title} placeholder="Post title" />
      <TextInput
        label="Slug (optional)"
        registration={register("slug")}
        error={errors.slug}
        placeholder="auto-generated-from-title-if-left-blank"
      />
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-text">Body</span>
        <BlogEditor ref={editorRef} initialContent={initialBody} />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {extraActions}
        <Button type="submit" loading={isSubmitting}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
};
