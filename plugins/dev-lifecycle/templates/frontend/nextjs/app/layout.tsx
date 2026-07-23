import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

// Root layout — a SERVER component (no "use client"): it renders the static
// <html>/<body> shell and delegates all client-side provider wiring to
// <Providers> (app/providers.tsx). Keeping this file server-only means the
// html/body shell itself never pulls the auth/query-client bundle into the
// server render — see app/page.tsx for the public landing page this buys.
export const metadata: Metadata = {
  title: {
    default: "Web App",
    template: "%s · Web App",
  },
  description: "Scaffolded Next.js (App Router) frontend — see the project README.",
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
