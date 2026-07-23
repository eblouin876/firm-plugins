import type { ReactNode } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import { Banner, Button } from "../form";
import { describeBlogError } from "./blogErrors";

/** The three state-changing, confirm-gated post actions this app exposes
 *  (list row + edit-page action bar) — everything except "Edit" (its own
 *  page, not a confirm-and-go action). */
export type BlogPostAction = "publish" | "unpublish" | "delete";

/** The subset of `BlogPostSummaryOut`/`BlogPostOut` this dialog actually
 *  needs — structurally satisfied by either, so the list page (which only
 *  has the summary shape) and the edit page (which has the full shape) can
 *  share this one dialog without a cast. */
interface BlogPostActionSubject {
  id: string;
  title: string;
}

export interface ConfirmPostActionTarget {
  post: BlogPostActionSubject;
  action: BlogPostAction;
}

interface ActionMeta {
  label: string;
  shortLabel: string;
  verb: string;
  note?: string;
  destructive?: boolean;
}

// Mirrors the backend's exact transition rules (see `app/api/routers/
// blog.py`): publish only from draft (409 if already published), unpublish
// only from published (409 if already draft, and it fully reverts to draft
// rather than leaving a stale `published_at`), delete has no status
// precondition. Same "offer only what's valid, but the server remains the
// authoritative check" posture as `components/users/actionMeta.ts`.
export const POST_ACTION_META: Record<BlogPostAction, ActionMeta> = {
  publish: {
    label: "Publish post",
    shortLabel: "Publish",
    verb: "publish",
  },
  unpublish: {
    label: "Unpublish post",
    shortLabel: "Unpublish",
    verb: "unpublish",
    note: "Reverts to draft. A later re-publish stamps a fresh publish date.",
  },
  delete: {
    label: "Delete post",
    shortLabel: "Delete",
    verb: "delete",
    note: "This soft-deletes the post — it stops appearing everywhere but the record is retained.",
    destructive: true,
  },
};

interface ConfirmPostActionDialogProps {
  /** `null` closes the dialog. */
  target: ConfirmPostActionTarget | null;
  pending: boolean;
  /** Set once the in-flight mutation for `target` rejects; cleared by the
   *  caller when a new target opens. */
  error: unknown;
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * The one confirm-and-go dialog shared by every per-post state action
 * (Publish/Unpublish/Delete) — same shape as `components/users/
 * ConfirmActionDialog.tsx`, adapted to a `BlogPostAction` subject instead of
 * a user. Used by both the list page (row actions) and the edit page (the
 * action bar next to Save).
 */
export const ConfirmPostActionDialog = ({
  target,
  pending,
  error,
  onConfirm,
  onClose,
}: ConfirmPostActionDialogProps): ReactNode => {
  const meta = target ? POST_ACTION_META[target.action] : null;

  return (
    <Dialog
      open={target !== null}
      onClose={() => {
        if (!pending) onClose();
      }}
      className="relative z-50"
    >
      <DialogBackdrop className="fixed inset-0 bg-black/30" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-lg">
          {target && meta && (
            <>
              <DialogTitle className="text-lg font-semibold">{meta.label}</DialogTitle>
              <p className="mt-2 text-sm text-muted">
                Are you sure you want to {meta.verb}{" "}
                <span className="font-medium text-text">{target.post.title}</span>?
                {meta.note && <span className="mt-1 block">{meta.note}</span>}
              </p>
              {error !== null && (
                <div className="mt-3">
                  <Banner tone="error">{describeBlogError(error)}</Banner>
                </div>
              )}
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="secondary" onClick={onClose} disabled={pending}>
                  Cancel
                </Button>
                <Button
                  variant={meta.destructive ? "danger" : "primary"}
                  onClick={onConfirm}
                  loading={pending}
                >
                  {meta.label}
                </Button>
              </div>
            </>
          )}
        </DialogPanel>
      </div>
    </Dialog>
  );
};
