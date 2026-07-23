import type { ReactNode } from "react";
import type { UseFormRegisterReturn, FieldError as RhfFieldError } from "react-hook-form";
import { Button as HeadlessButton, Field, Input, Label } from "@headlessui/react";
import { FieldError } from "@repo/web-shared";

// A tiny, token-driven form kit built on Headless UI's accessible primitives
// (`Field`/`Label`/`Input` wire the label<->input association and invalid/aria
// state for us) + Tailwind utilities that reference the theme tokens only —
// never a raw hex/px (see references/frontend/tailwind.md, "Design tokens").
// The design-system skill owns the tokens; these components just consume them.

const cx = (...parts: Array<string | false | undefined>): string =>
  parts.filter(Boolean).join(" ");

interface TextInputProps {
  label: string;
  /** Spread of `register("field")` from react-hook-form. */
  registration: UseFormRegisterReturn;
  /** The RHF field error (or a plain message) to surface under the input. */
  error?: RhfFieldError | string;
  type?: "text" | "email" | "password";
  autoComplete?: string;
  placeholder?: string;
}

/** Labelled text input + inline validation message. */
export const TextInput = ({
  label,
  registration,
  error,
  type = "text",
  autoComplete,
  placeholder,
}: TextInputProps): ReactNode => (
  <Field className="flex flex-col gap-1.5">
    <Label className="text-sm font-medium text-text">{label}</Label>
    <Input
      type={type}
      autoComplete={autoComplete}
      placeholder={placeholder}
      invalid={Boolean(error)}
      className={cx(
        "rounded-md border border-border bg-surface px-3 py-2 text-text",
        "outline-none focus-visible:ring-2 focus-visible:ring-primary",
        "data-[invalid]:border-danger",
      )}
      {...registration}
    />
    <FieldError error={error} />
  </Field>
);

interface ButtonProps {
  children: ReactNode;
  type?: "button" | "submit";
  variant?: "primary" | "secondary" | "danger";
  /** "sm" is the compact size used for dense contexts like per-row table
   *  actions; "md" (default) is the normal form/dialog size. */
  size?: "sm" | "md";
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

/** Themed button (Headless UI `Button` for its focus/disabled behavior). */
export const Button = ({
  children,
  type = "button",
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  onClick,
}: ButtonProps): ReactNode => (
  <HeadlessButton
    type={type}
    onClick={onClick}
    disabled={disabled || loading}
    className={cx(
      "inline-flex items-center justify-center rounded-md font-medium",
      size === "sm" ? "px-2.5 py-1 text-xs" : "px-4 py-2 text-sm",
      "outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60",
      variant === "primary" &&
        "bg-primary text-primary-foreground hover:bg-primary-hover",
      variant === "secondary" && "border border-border bg-surface text-text hover:bg-bg",
      variant === "danger" && "bg-danger text-primary-foreground hover:opacity-90",
    )}
  >
    {loading ? "Working…" : children}
  </HeadlessButton>
);

interface BannerProps {
  tone?: "error" | "success" | "info";
  children: ReactNode;
}

/** Inline status/error banner. `error` gets `role="alert"` (assertively
 *  announced); the rest get `role="status"`. */
export const Banner = ({ tone = "info", children }: BannerProps): ReactNode => (
  <p
    role={tone === "error" ? "alert" : "status"}
    className={cx(
      "rounded-md border px-3 py-2 text-sm",
      tone === "error" && "border-danger text-danger",
      tone === "success" && "border-success text-success",
      tone === "info" && "border-border text-muted",
    )}
  >
    {children}
  </p>
);
