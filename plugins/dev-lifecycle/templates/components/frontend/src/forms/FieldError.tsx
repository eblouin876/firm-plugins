import type { ReactNode } from "react";
import type { FieldError as RhfFieldError } from "react-hook-form";

interface FieldErrorProps {
  /**
   * Either a plain message string, or an RHF field-error object (e.g.
   * `formState.errors.email`) whose `.message` is read. Renders nothing when
   * there's no message, so it's safe to drop under every field
   * unconditionally.
   */
  error?: string | RhfFieldError;
}

/**
 * Minimal, unstyled field-error line with `role="alert"` (announced by screen
 * readers and easily queried in tests). Bring your own styling via the
 * `field-error` class or wrap it; this stays framework/design-system-neutral.
 */
export const FieldError = ({ error }: FieldErrorProps): ReactNode => {
  const message = typeof error === "string" ? error : error?.message;
  if (!message) return null;
  return (
    <p role="alert" className="field-error">
      {message}
    </p>
  );
};
