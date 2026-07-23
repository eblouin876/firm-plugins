import { ApiError, isApiError } from "@repo/web-shared";

/**
 * Turn a caught error into a user-facing message for the blog screens —
 * same idiom as `components/users/actionMeta.ts`'s `describeApiError`
 * (kept as its own small copy here rather than a cross-import, matching
 * that module's own self-contained-per-feature-folder convention). Prefers
 * the SERVER's own message from an `ApiError`'s envelope (e.g. "A post with
 * this slug already exists.", "Cannot publish a post that is already
 * published.") over the generic `errorCodeToMessage` fallback.
 */
export const describeBlogError = (error: unknown): string => {
  if (isApiError(error)) return error.envelope?.error.message ?? error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
};

export { ApiError, isApiError };
