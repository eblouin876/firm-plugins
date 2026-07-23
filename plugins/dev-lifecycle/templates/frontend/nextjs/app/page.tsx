import type { Metadata } from "next";

// The public landing page — a SERVER component with NO auth check and NO
// client-auth bundle. This is the honest SSR win over the Vite SPA: this
// route is statically rendered at build time (no `AuthProvider`/QueryClient
// JS needs to hydrate here at all, since the page renders no client
// component itself), unlike the SPA where every route — public or not —
// ships the same single JS bundle. Authenticated surfaces (sub-agent B's
// `(app)` route group) stay client-rendered, same posture as the SPA.
export const metadata: Metadata = {
  title: "Home",
  description:
    "A scaffolded Next.js (App Router) + FastAPI/Django starter app — sign in to get started.",
};

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight text-text">Web App</h1>
      <p className="max-w-prose text-lg text-muted">
        This is the public, server-rendered landing page — no auth required, no client-auth
        bundle shipped here. Sign in to reach the authenticated app surfaces.
      </p>
      <a
        href="/login"
        className="rounded-md bg-primary px-5 py-2.5 font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
      >
        Sign in
      </a>
    </main>
  );
}
