import type { ReactNode } from "react";

interface ComingSoonProps {
  title: string;
  note: string;
}

/**
 * Minimal placeholder for a stub feature page (`users`, `moderation`,
 * `blog` — see `app/(app)/*`). Each of those pages is admin-gated purely by
 * inheriting `app/(app)/layout.tsx`'s whole-app gate; this component carries
 * no auth logic of its own. Real content replaces each stub's usage of this
 * component page-by-page as the later admin-tool stages land — this
 * component itself is not expected to survive past that point.
 */
export const ComingSoon = ({ title, note }: ComingSoonProps): ReactNode => (
  <div className="flex flex-col gap-2">
    <h1 className="text-2xl font-semibold">{title}</h1>
    <p className="text-muted">Coming soon — {note}</p>
  </div>
);
