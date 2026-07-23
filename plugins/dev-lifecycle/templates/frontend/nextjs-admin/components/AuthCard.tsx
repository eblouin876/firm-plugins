import type { ReactNode } from "react";

interface AuthCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Optional footer slot (e.g. a link to another auth screen). */
  footer?: ReactNode;
}

/**
 * Centered single-card layout shared by the public auth screens
 * (login/register/verify/forgot/reset). No shell/header — those routes render
 * outside the authenticated `(app)` layout.
 */
export const AuthCard = ({ title, subtitle, children, footer }: AuthCardProps): ReactNode => (
  <div className="flex min-h-screen items-center justify-center bg-bg px-4 py-12 text-text">
    <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-sm">
      <h1 className="text-xl font-semibold">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      <div className="mt-6">{children}</div>
      {footer && <div className="mt-6 text-sm text-muted">{footer}</div>}
    </div>
  </div>
);
