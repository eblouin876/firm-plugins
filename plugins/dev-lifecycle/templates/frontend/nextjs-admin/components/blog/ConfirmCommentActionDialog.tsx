import type { ReactNode } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import type { CommentOut } from "@repo/api-client";
import { Banner, Button } from "../form";
import { describeBlogError } from "./blogErrors";

/** The two confirm-gated comment actions this lightweight view exposes.
 *  NOT the Stage 13c Flag/Report moderation surface — see this module's own
 *  note in `app/(app)/blog/comments/page.tsx`. */
export type CommentAction = "hide" | "delete";

export interface ConfirmCommentActionTarget {
  comment: CommentOut;
  action: CommentAction;
}

interface ActionMeta {
  label: string;
  shortLabel: string;
  verb: string;
  note?: string;
  destructive?: boolean;
}

// Mirrors the backend's transition rule (`app/api/routers/blog.py`'s
// `hide_admin_blog_comment`): hide is valid from `visible`/`pending`, 409 if
// already hidden (idempotent re-hide rejected). Delete has no precondition.
export const COMMENT_ACTION_META: Record<CommentAction, ActionMeta> = {
  hide: {
    label: "Hide comment",
    shortLabel: "Hide",
    verb: "hide",
  },
  delete: {
    label: "Delete comment",
    shortLabel: "Delete",
    verb: "delete",
    note: "This soft-deletes the comment — it stops appearing everywhere but the record is retained.",
    destructive: true,
  },
};

interface ConfirmCommentActionDialogProps {
  target: ConfirmCommentActionTarget | null;
  pending: boolean;
  error: unknown;
  onConfirm: () => void;
  onClose: () => void;
}

/** Same confirm-and-go dialog shape as `ConfirmPostActionDialog`/
 *  `components/users/ConfirmActionDialog.tsx`, adapted to a comment. */
export const ConfirmCommentActionDialog = ({
  target,
  pending,
  error,
  onConfirm,
  onClose,
}: ConfirmCommentActionDialogProps): ReactNode => {
  const meta = target ? COMMENT_ACTION_META[target.action] : null;

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
                Are you sure you want to {meta.verb} this comment?
                {meta.note && <span className="mt-1 block">{meta.note}</span>}
              </p>
              <p className="mt-2 rounded-md bg-bg p-2 text-sm text-muted">{target.comment.body}</p>
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
