import { ApiError, isApiError } from "@repo/web-shared";

/**
 * Turn a caught error into a user-facing message for the moderation queue —
 * same idiom as `components/users/actionMeta.ts`'s `describeApiError` /
 * `components/blog/blogErrors.ts`'s `describeBlogError` (kept as its own
 * small copy here rather than a cross-import, matching those modules' own
 * self-contained-per-feature-folder convention). Prefers the SERVER's own
 * message from an `ApiError`'s envelope — e.g. "Cannot resolve a flag with
 * status 'resolved'." (409, already-resolved/dismissed), "An admin cannot
 * ban their own account." (409, ban-author self-protection), or
 * "hide_content is not a valid action for a 'user' target." (422) — over the
 * generic `errorCodeToMessage` fallback.
 */
export const describeModerationError = (error: unknown): string => {
  if (isApiError(error)) return error.envelope?.error.message ?? error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
};

export { ApiError, isApiError };
