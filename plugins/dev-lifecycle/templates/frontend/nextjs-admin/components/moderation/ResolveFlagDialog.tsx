"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import { FlagTargetType, ResolveAction } from "@repo/api-client";
import type { FlagOut } from "@repo/api-client";
import { Banner, Button } from "../form";
import { describeModerationError } from "./moderationErrors";

export interface ResolveFlagTarget {
  flag: FlagOut;
}

export interface ResolveFlagPayload {
  action: ResolveAction;
  note?: string;
}

interface ResolveActionOption {
  value: ResolveAction;
  label: string;
  hint: string;
}

// Every action offered for a `blog_post`/`comment` target. Mirrors
// `app/api/routers/moderation.py`'s `resolve_admin_flag` dispatch: `none`
// just closes the report, `hide_content`/`delete_content` act on the
// flagged content itself, `ban_author` bans whoever authored it.
const CONTENT_ACTIONS: ResolveActionOption[] = [
  {
    value: ResolveAction.none,
    label: "None — just close the report",
    hint: "Marks the flag resolved. No content or account changes.",
  },
  {
    value: ResolveAction.hide_content,
    label: "Hide content",
    hint: "Unpublishes the blog post, or hides the comment.",
  },
  {
    value: ResolveAction.delete_content,
    label: "Delete content",
    hint: "Soft-deletes the post or comment — it stops appearing everywhere but the record is retained.",
  },
  {
    value: ResolveAction.ban_author,
    label: "Ban author",
    hint: "Bans the account that authored the flagged content.",
  },
];

// A `user` target has no content to hide or delete — the backend 422s
// `hide_content`/`delete_content` for it (`_hide_content`/`_delete_content`
// in `app/api/routers/moderation.py`) — so only `none`/`ban_author` are
// offered here. This is UX guidance only: the backend remains the
// authoritative gate, and `describeModerationError` below is the backstop
// if a stale client ever posts an invalid action anyway.
const USER_ACTIONS: ResolveActionOption[] = [
  {
    value: ResolveAction.none,
    label: "None — just close the report",
    hint: "Marks the flag resolved. No account changes.",
  },
  {
    value: ResolveAction.ban_author,
    label: "Ban user",
    hint: "Bans this account directly.",
  },
];

const actionsFor = (targetType: FlagTargetType): ResolveActionOption[] =>
  targetType === FlagTargetType.user ? USER_ACTIONS : CONTENT_ACTIONS;

interface ResolveFlagDialogProps {
  /** `null` closes the dialog. */
  target: ResolveFlagTarget | null;
  pending: boolean;
  /** Set once the in-flight mutation for `target` rejects; cleared by the
   *  caller when a new target opens. */
  error: unknown;
  onConfirm: (payload: ResolveFlagPayload) => void;
  onClose: () => void;
}

/**
 * The resolve dialog for an `open` flag — an action selector (guided by
 * `target.flag.target_type`, see `actionsFor` above) plus an optional free-
 * text note, submitting `POST /admin/flags/{id}/resolve {action, note}`.
 * Same "presentational dialog, mutation lives in the page" shape as
 * `components/users/ConfirmActionDialog.tsx`, extended with the extra
 * inputs this action needs. `key={target.flag.id}` on the inner form
 * forces a fresh mount (fresh local state) every time a different flag
 * opens, same trick `components/users/RolesDialog.tsx` uses.
 */
export const ResolveFlagDialog = ({
  target,
  pending,
  error,
  onConfirm,
  onClose,
}: ResolveFlagDialogProps): ReactNode => (
  <Dialog
    open={target !== null}
    onClose={() => {
      if (!pending) onClose();
    }}
    className="relative z-50"
  >
    <DialogBackdrop className="fixed inset-0 bg-black/30" />
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel className="w-full max-w-md rounded-lg border border-border bg-surface p-6 shadow-lg">
        {target && (
          <ResolveFlagForm
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

const ResolveFlagForm = ({
  flag,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  flag: FlagOut;
  pending: boolean;
  error: unknown;
  onConfirm: (payload: ResolveFlagPayload) => void;
  onClose: () => void;
}): ReactNode => {
  const options = actionsFor(flag.target_type);
  const [action, setAction] = useState<ResolveAction>(ResolveAction.none);
  const [note, setNote] = useState("");
  const selected = options.find((option) => option.value === action) ?? options[0];
  const destructive = action === ResolveAction.delete_content || action === ResolveAction.ban_author;

  const submit = (): void => {
    const trimmed = note.trim();
    onConfirm({ action, note: trimmed.length > 0 ? trimmed : undefined });
  };

  return (
    <>
      <DialogTitle className="text-lg font-semibold">Resolve flag</DialogTitle>
      <p className="mt-1 text-sm text-muted">
        <span className="font-medium capitalize text-text">{flag.target_type.replace("_", " ")}</span>{" "}
        <span className="font-mono text-xs">{flag.target_id}</span>
      </p>
      <p className="mt-2 rounded-md bg-bg p-2 text-sm text-muted">{flag.reason}</p>

      <div className="mt-4 flex flex-col gap-1.5">
        <label htmlFor="resolve-action" className="text-sm font-medium text-text">
          Action
        </label>
        <select
          id="resolve-action"
          value={action}
          onChange={(event) => setAction(event.target.value as ResolveAction)}
          disabled={pending}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {selected && <p className="text-xs text-muted">{selected.hint}</p>}
      </div>

      <div className="mt-4 flex flex-col gap-1.5">
        <label htmlFor="resolve-note" className="text-sm font-medium text-text">
          Note (optional)
        </label>
        <textarea
          id="resolve-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          disabled={pending}
          rows={3}
          placeholder="Context for this decision (visible to other admins)."
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
        <Button variant={destructive ? "danger" : "primary"} onClick={submit} loading={pending}>
          Resolve
        </Button>
      </div>
    </>
  );
};
