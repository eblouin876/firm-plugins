import { ApiError, isApiError } from "@repo/web-shared";

/**
 * The five state-changing, confirm-gated admin actions this page exposes on
 * a row — everything except "Edit roles" (its own dialog/form, not a single
 * confirm-and-go action). Kept as a closed string union so `ACTION_META`
 * below is exhaustively checked by the compiler.
 */
export type UserAction = "suspend" | "ban" | "reinstate" | "force-verify" | "delete";

interface ActionMeta {
  /** Dialog title / confirm button label. */
  label: string;
  /** Compact label for the per-row trigger button (table columns are tight). */
  shortLabel: string;
  /** Verb used in the confirmation sentence ("suspend", "ban", ...). */
  verb: string;
  /** Extra context shown under the confirmation sentence. */
  note?: string;
  /** Renders the confirm button in the danger variant. */
  destructive?: boolean;
}

// Mirrors the backend's exact transition rules (see
// `app/api/routers/admin.py`): suspend only from active, ban from
// active/suspended, reinstate from suspended/banned, force-verify is
// idempotent, delete is a soft-delete. Every one of these is also
// self-protected server-side (409 if the acting admin targets their own
// account) — this page does not try to pre-empt that client-side (see
// `app/(app)/users/page.tsx`'s docstring); it just surfaces the 409 the
// server sends back.
export const ACTION_META: Record<UserAction, ActionMeta> = {
  suspend: {
    label: "Suspend user",
    shortLabel: "Suspend",
    verb: "suspend",
    note: "They'll be signed out everywhere and unable to sign back in until reinstated.",
  },
  ban: {
    label: "Ban user",
    shortLabel: "Ban",
    verb: "ban",
    note: "They'll be signed out everywhere and unable to sign back in until reinstated.",
    destructive: true,
  },
  reinstate: {
    label: "Reinstate user",
    shortLabel: "Reinstate",
    verb: "reinstate",
    note: "Restores normal sign-in access.",
  },
  "force-verify": {
    label: "Force-verify email",
    shortLabel: "Force-verify",
    verb: "force-verify the email for",
  },
  delete: {
    label: "Delete user",
    shortLabel: "Delete",
    verb: "delete",
    note: "This soft-deletes the account — it stops appearing everywhere but the record is retained.",
    destructive: true,
  },
};

/**
 * Turn a caught error into a user-facing message. For an `ApiError` carrying
 * a server envelope, prefer the SERVER's own message (e.g. "An admin cannot
 * suspend their own account.", "Cannot ban a user with status 'banned'.") —
 * that's the specific, actionable text for a 409 conflict or a 404; falling
 * back to `ApiError.message` (the generic `errorCodeToMessage` copy) only
 * when there's no envelope to read a message from. Anything that isn't an
 * `ApiError` at all (a network failure, a thrown non-Error) gets a safe
 * generic string — this must never throw or return `undefined`.
 */
export const describeApiError = (error: unknown): string => {
  if (isApiError(error)) return error.envelope?.error.message ?? error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
};

// Re-exported so callers of this module don't also need a direct
// `@repo/web-shared` import just for the `instanceof` check.
export { ApiError, isApiError };
