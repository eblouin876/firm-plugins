import type { ReactNode } from "react";
import { z } from "zod";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import type { AdminUserOut } from "@repo/api-client";
import { useSetAdminUserRolesAdminUsersUserIdRolesPut } from "@repo/api-client";
import { applyEnvelopeToForm, unwrap, useZodForm } from "@repo/web-shared";
import { Banner, Button, TextInput } from "../form";
import { describeApiError } from "./actionMeta";

const schema = z.object({
  roles: z.string().min(1, "Enter at least one role."),
});
type Values = z.infer<typeof schema>;

/**
 * Parse the comma/whitespace-separated roles text field into the
 * deduplicated string list `AdminRolesIn` expects. The backend does its own
 * dedupe/sort on write (`set_admin_user_roles`'s `deduped = sorted(set(...))`)
 * — this just normalizes what the admin typed before sending it.
 */
const parseRoles = (text: string): string[] => {
  const seen = new Set<string>();
  for (const raw of text.split(/[,\s]+/)) {
    const role = raw.trim();
    if (role) seen.add(role);
  }
  return [...seen];
};

interface RolesDialogProps {
  /** `null` closes the dialog. */
  user: AdminUserOut | null;
  onClose: () => void;
  /** Fires after a successful `PUT .../roles` — caller invalidates the list
   *  query and closes the dialog. */
  onSuccess: () => void;
}

/**
 * Full-replace role editor for `PUT /admin/users/{id}/roles`. A single free-
 * text field (comma/space-separated) rather than a dynamic add/remove list
 * of checkboxes — the allowed-role set is a small, closed, app-level policy
 * the BACKEND validates (an unknown role raises `ValidationFailedError`, 422
 * `validation_failed`, one `ErrorDetail` per bad role with `field: "roles"`)
 * -- so a free-text input + surfacing that 422 via `applyEnvelopeToForm`
 * (which sets the error on the exact `"roles"` field name below) is simpler
 * than duplicating the closed role set client-side and just as safe: no
 * write happens until the server itself has validated every role.
 */
export const RolesDialog = ({ user, onClose, onSuccess }: RolesDialogProps): ReactNode => (
  <Dialog open={user !== null} onClose={onClose} className="relative z-50">
    <DialogBackdrop className="fixed inset-0 bg-black/30" />
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-lg">
        {/* `key={user.id}` forces a fresh mount (fresh RHF defaultValues)
            every time the dialog opens for a (possibly different) user. */}
        {user && <RolesForm key={user.id} user={user} onClose={onClose} onSuccess={onSuccess} />}
      </DialogPanel>
    </div>
  </Dialog>
);

const RolesForm = ({
  user,
  onClose,
  onSuccess,
}: {
  user: AdminUserOut;
  onClose: () => void;
  onSuccess: () => void;
}): ReactNode => {
  const setRoles = useSetAdminUserRolesAdminUsersUserIdRolesPut();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { roles: user.roles.join(", ") } });

  const onSubmit = handleSubmit(async (values: Values) => {
    const roles = parseRoles(values.roles);
    if (roles.length === 0) {
      setError("roles", { message: "Enter at least one role." });
      return;
    }
    try {
      unwrap(await setRoles.mutateAsync({ userId: user.id, data: { roles } }));
      onSuccess();
    } catch (err) {
      // 422 validation_failed (an unknown role) lands on the "roles" field;
      // anything else (409 self-protection dropping own admin role, etc.)
      // falls back to a form-level banner with the server's own message.
      if (applyEnvelopeToForm(err, setError)) return;
      setError("root", { message: describeApiError(err) });
    }
  });

  return (
    <>
      <DialogTitle className="text-lg font-semibold">Edit roles</DialogTitle>
      <p className="mt-1 text-sm text-muted">
        <span className="font-medium text-text">{user.email}</span> — comma or space separated.
      </p>
      <form onSubmit={onSubmit} noValidate className="mt-4 flex flex-col gap-4">
        {errors.root?.message && <Banner tone="error">{errors.root.message}</Banner>}
        <TextInput
          label="Roles"
          registration={register("roles")}
          error={errors.roles}
          placeholder="admin, editor"
        />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" loading={isSubmitting}>
            Save roles
          </Button>
        </div>
      </form>
    </>
  );
};
