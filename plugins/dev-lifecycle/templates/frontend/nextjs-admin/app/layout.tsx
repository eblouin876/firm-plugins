import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

// Root layout — a SERVER component (no "use client"): it renders the static
// <html>/<body> shell and delegates all client-side provider wiring to
// <Providers> (app/providers.tsx). Unlike the `web` app, there is no public
// route in this tree at all (app/page.tsx just redirects to /dashboard), so
// this file being server-only buys less here than it does there — kept
// anyway for parity with the clone source and because Providers still must
// not double-mount across Fast Refresh.
export const metadata: Metadata = {
  title: {
    default: "Admin",
    template: "%s · Admin",
  },
  description: "Standalone admin tool — see the project README. Admin-role required.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
