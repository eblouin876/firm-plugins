"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import type { FlagOut } from "@repo/api-client";
import { Banner, Button } from "../form";
import { describeModerationError } from "./moderationErrors";

export interface DismissFlagTarget {
  flag: FlagOut;
}

export interface DismissFlagPayload {
  note?: string;
}

interface DismissFlagDialogProps {
  /** `null` closes the dialog. */
  target: DismissFlagTarget | null;
  pending: boolean;
  /** Set once the in-flight mutation for `target` rejects; cleared by the
   *  caller when a new target opens. */
  error: unknown;
  onConfirm: (payload: DismissFlagPayload) => void;
  onClose: () => void;
}

/**
 * The dismiss dialog for an `open` flag — an optional free-text note,
 * submitting `POST /admin/flags/{id}/dismiss {note}`. Dismiss never touches
 * content or an account (see `app/api/routers/moderation.py`'s
 * `dismiss_admin_flag` docstring: "this report doesn't warrant action"), so
 * there's no action selector here, unlike `ResolveFlagDialog`.
 */
export const DismissFlagDialog = ({
  target,
  pending,
  error,
  onConfirm,
  onClose,
}: DismissFlagDialogProps): ReactNode => (
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
        {target && (
          <DismissFlagForm
            key={target.flag.id}
            flag={target.flag}
            pending={pending}
            error={error}
            onConfirm={onConfirm}
            onClose={onClose}
          />
        )}
      </DialogPanel>
    </div>
  </Dialog>
);

const DismissFlagForm = ({
  flag,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  flag: FlagOut;
  pending: boolean;
  error: unknown;
  onConfirm: (payload: DismissFlagPayload) => void;
  onClose: () => void;
}): ReactNode => {
  const [note, setNote] = useState("");

  const submit = (): void => {
    const trimmed = note.trim();
    onConfirm({ note: trimmed.length > 0 ? trimmed : undefined });
  };

  return (
    <>
      <DialogTitle className="text-lg font-semibold">Dismiss flag</DialogTitle>
      <p className="mt-1 text-sm text-muted">
        <span className="font-medium capitalize text-text">{flag.target_type.replace("_", " ")}</span>{" "}
        <span className="font-mono text-xs">{flag.target_id}</span>
      </p>
      <p className="mt-2 rounded-md bg-bg p-2 text-sm text-muted">{flag.reason}</p>

      <div className="mt-4 flex flex-col gap-1.5">
        <label htmlFor="dismiss-note" className="text-sm font-medium text-text">
          Note (optional)
        </label>
        <textarea
          id="dismiss-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          disabled={pending}
          rows={3}
          placeholder="Why this report doesn't warrant action (visible to other admins)."
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
        />
      </div>

      {error !== null && (
        <div className="mt-3">
          <Banner tone="error">{describeModerationError(error)}</Banner>
        </div>
      )}

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending}>
          Dismiss
        </Button>
      </div>
    </>
  );
};
