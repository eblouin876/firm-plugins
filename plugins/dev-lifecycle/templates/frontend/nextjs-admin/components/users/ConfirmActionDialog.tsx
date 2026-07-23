import type { ReactNode } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import type { AdminUserOut } from "@repo/api-client";
import { Banner, Button } from "../form";
import { ACTION_META, describeApiError } from "./actionMeta";
import type { UserAction } from "./actionMeta";

export interface ConfirmActionTarget {
  user: AdminUserOut;
  action: UserAction;
}

interface ConfirmActionDialogProps {
  /** `null` closes the dialog. */
  target: ConfirmActionTarget | null;
  pending: boolean;
  /** Set once the in-flight mutation for `target` rejects; cleared by the
   *  caller when a new target opens. */
  error: unknown;
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * The one confirm-and-go dialog shared by every per-row destructive/state
 * action (Suspend/Ban/Reinstate/Force-verify/Delete) — see `ACTION_META` for
 * the per-action copy. Deliberately generic rather than five near-identical
 * dialogs: the only thing that varies per action is the label/verb/note/
 * destructive-ness, all read off `ACTION_META[target.action]`.
 */
export const ConfirmActionDialog = ({
  target,
  pending,
  error,
  onConfirm,
  onClose,
}: ConfirmActionDialogProps): ReactNode => {
  const meta = target ? ACTION_META[target.action] : null;

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
                <span className="font-medium text-text">{target.user.email}</span>?
                {meta.note && <span className="mt-1 block">{meta.note}</span>}
              </p>
              {error !== null && (
                <div className="mt-3">
                  <Banner tone="error">{describeApiError(error)}</Banner>
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
