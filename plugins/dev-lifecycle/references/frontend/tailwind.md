<!--
library: tailwind
versions-covered: "3, 4"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://tailwindcss.com/docs
  - https://tailwindcss.com/blog/tailwindcss-v4
-->

# Tailwind CSS conventions

Granular guidance for styling with Tailwind. Read after detecting `tailwindcss`. Subordinate to the project's existing config/theme. Applies to both the React path and the HTMX path (see `htmx.md`).

## Contents
- Version check (do this first)
- Configuration (v4 is CSS-first)
- Utility discipline
- Design tokens
- Component extraction
- Dark mode & state
- Accessibility & readability

## Version check (do this first)
**v3 and v4 are configured very differently — check which is installed.**

- **Tailwind v4** (current; latest in the 4.3 line) is a ground-up rewrite (Oxide engine) and is **CSS-first**:
  - Import with `@import "tailwindcss";` in your CSS — no `@tailwind base/components/utilities` directives.
  - **Configuration lives in CSS** via the `@theme` directive; `tailwind.config.js` is no longer required (a JS config can still be referenced, but tokens as CSS custom properties are the idiom). Defining `--color-brand: …` in `@theme` generates `bg-brand`, `text-brand`, etc.
  - **Automatic content detection** — template files are discovered without a `content` array; add extras with `@source`.
  - First-party **Vite** and **webpack** plugins (no separate PostCSS chain needed).
  - **OKLCH** colors by default; container queries and logical properties are first-class.
  - Requires modern browsers (Safari 16.4+, Chrome 111+, Firefox 128+).
- **v3→v4 migration:** run `npx @tailwindcss/upgrade` (handles ~90% mechanically). The most widespread rename is `bg-gradient-to-*` → `bg-linear-to-*`; `@apply` behavior changed; config moves from JS to CSS. Review custom plugins by hand.
- **Tailwind v3**: JS `tailwind.config.js` with the `content` array and `@tailwind` directives. Match it; don't write v4 CSS-first idioms into a v3 project.

If unsure whether a utility/name exists in the installed major, check the current docs — v4 renamed a batch of legacy aliases.

## Configuration (v4)
- Put design tokens in `@theme` as CSS variables — this is where the `design-system` skill's tokens live, and it makes runtime theme switching possible without a rebuild (override the variables under `:root` / `[data-theme]`).
- Keep the CSS entry lean and documented; don't scatter `@theme` blocks across many files.

## Utility discipline
- Utility-first in the markup; that's the point — don't prematurely abstract into custom CSS.
- **Use tokens, not arbitrary values, when a token exists.** `p-4`, `text-brand`, `gap-2` over `p-[17px]`, `text-[#764abc]`. Arbitrary values are an escape hatch for genuine one-offs, not the default.
- Keep class lists readable: order by concern (layout → box → typography → color → state), consistent with the codebase.

## Design tokens
- Color, spacing, typography, and radii come from the theme (`@theme` in v4, `theme.extend` in v3), owned by the `design-system` skill. A component reaching for a raw hex or pixel value is a smell — add or use a token instead.
- v4's OKLCH palette gives more uniform color; custom colors accept any format (hex/rgb/oklch).

## Component extraction
- Extract only on **genuine** repetition. For React, extract a component (preferred) so the class list lives in one place; for HTMX/templates, extract a partial/include.
- Prefer a shared component over `@apply`-ing utilities into a bespoke class — `@apply` drifts and its v4 behavior changed. Use it sparingly, for small, stable primitives.

## Dark mode & state
- Use the project's dark-mode strategy (class or `data-*` attribute) consistently; drive it from CSS-variable overrides in v4 rather than duplicating whole style sets.
- Use state variants (`hover:`, `focus-visible:`, `disabled:`, `aria-*:`, `data-*:`) rather than JS toggling classes where CSS can express it.

## Accessibility & readability
- `focus-visible:` for keyboard focus rings — don't remove focus styling.
- Ensure contrast meets WCAG minimums for token color pairings; color is never the sole carrier of meaning.
- Don't let a 15-utility class list bury meaning — extract when it hurts readability, not before.
