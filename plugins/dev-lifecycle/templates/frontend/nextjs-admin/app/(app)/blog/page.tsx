import type { ReactNode } from "react";
import { ComingSoon } from "../../../components/ComingSoon";

// Stub feature page — resolves the "Blog" nav link and proves the route
// builds, admin-gated purely by inheriting `app/(app)/layout.tsx`'s whole-app
// <ProtectedGate><AdminGate>. The real blog editor (Stage 13d) will use the
// TipTap rich-text stack pinned in references/compatibility-matrix.md's
// "Editor (WYSIWYG)" section (@tiptap/react, @tiptap/pm, @tiptap/starter-kit,
// @tiptap/extension-link) — deliberately NOT added to this app's package.json
// yet (no unused dep in the shell); that lands with the editor stage itself.
export default function BlogPage(): ReactNode {
  return (
    <ComingSoon
      title="Blog"
      note="The blog editor (TipTap-based) lands in a later admin-tool stage."
    />
  );
}
