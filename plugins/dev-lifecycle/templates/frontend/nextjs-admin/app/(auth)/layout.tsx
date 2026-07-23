import type { ReactNode } from "react";

// The public auth route group's layout: deliberately EMPTY app chrome. The
// single screen below (`login`) renders its own centered `<AuthCard>` (see
// `components/AuthCard.tsx`), the same "no shell/header" posture as the
// `web` app's auth routes. No auth check here — this IS the public login
// screen. Unlike the `web` app, there's no register/verify/forgot/reset
// here — admins are seeded, not self-signup (see this block's README).
export default function AuthLayout({ children }: { children: ReactNode }) {
  return children;
}
