import { redirect } from "next/navigation";

// An admin tool has no public landing page — unlike the `web` app's
// `app/page.tsx` (a marketing/sign-in page rendered for anonymous visitors),
// `/` here is not a real screen at all. A SERVER component doing a plain
// `redirect()` (from `next/navigation`) is the clean App Router idiom for
// this: no client-auth bundle ships for this route, no flash of unstyled
// content, and no extra round trip through a client-side
// `useEffect`/`useRouter` redirect. `redirect()` throws a special Next.js
// control-flow signal the framework itself catches, so this function never
// "returns" a value in the normal sense — see Next's own docs on `redirect`
// for that mechanic.
//
// `/dashboard` is itself admin-gated (see `app/(app)/layout.tsx`'s whole-app
// `<ProtectedGate><AdminGate>` wrap), so the actual auth/role enforcement
// happens there, not here: an anonymous visitor bounces on to `/login`
// (`ProtectedGate`'s fallback), and a signed-in non-admin bounces back to
// `/dashboard` itself (`AdminGate`'s fallback, which just re-renders past
// `ProtectedGate` without the admin content) — a non-admin has nowhere
// valid to land in this app, which is the intended, fully-locked-out
// posture for a whole-app-admin-gated tool (the backend's 403 on
// `/admin/ping` is the authoritative gate regardless).
export default function RootPage() {
  redirect("/dashboard");
}
