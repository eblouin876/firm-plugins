---
name: "design-system"
description: "Establish and enforce a project's visual design system — the design tokens (color, typography, spacing, radii, shadows, breakpoints), component conventions, and accessibility standards that the frontend, tailwind, and material-ui work is written to defer to. Use this skill WHENEVER the work is about the system rather than one screen: \"set up the design system\", \"define our tokens/theme\", \"make the styling consistent\", \"what should our color/type scale be\", \"enforce the design standards\", or when new UI needs a token that doesn't exist yet. It detects and conforms to any system already present. It defines the standards; the frontend skill builds against them."
---

# Design system

Own the project's visual language as a single source of truth, so every screen is consistent and no component hardcodes a color or a pixel. This skill defines and maintains the **tokens** and conventions; `frontend` (with `tailwind` / `material-ui`) builds against them, and `ui-exploration` feeds it new directions. It is the system, not the screens.

## Core rules

- **Tokens are the single source of truth.** Every color, spacing, type, radius, and shadow value a component uses comes from a named token defined once — in Tailwind v4's `@theme` (see `${CLAUDE_PLUGIN_ROOT}/references/frontend/tailwind.md`), MUI's `createTheme` (see `${CLAUDE_PLUGIN_ROOT}/references/frontend/material-ui.md`), or CSS custom properties. A hardcoded hex or pixel in a component is a defect.
- **Semantic, not literal.** Name tokens by role (`color.surface`, `color.text.muted`, `space.4`), not by value (`gray-100`), so themes and dark mode swap cleanly.
- **Detect and conform.** Read the existing system (theme config, tokens, CSS vars) and extend it. Don't impose a new system on a project that has one.
- **Accessibility is part of the system.** Contrast-safe color pairings (WCAG AA), a legible type scale, visible focus, and respect for reduced motion are defined *in the system*, so every component inherits them.
- **Right-size.** Match the token and component set to the project — a lean, coherent set beats an aspirational component library nobody uses.
- **Define, don't build.** This skill sets the standards and the tokens; feature UI is the `frontend` skill's job.

## Workflow

### 1. Detect the current system
Read what exists: Tailwind config / `@theme` block, MUI theme, CSS custom properties, any token file or Figma export referenced. Note the conventions already in use and conform to them. Work context-efficiently — read the theme/config, not every component (`${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`).

### 2. Establish or extend the tokens
Define the token set the project needs, once, in its chosen mechanism:
- **Color** — semantic roles (primary/accent, surface/background, text and muted text, border, and state colors: success/warning/danger/info), each with the pairings that pass contrast. Include dark-mode values if in scope.
- **Typography** — family/families, a type scale, weights, line-heights.
- **Spacing** — a consistent scale (don't invent one-off gaps).
- **Radii, shadows, borders, breakpoints, z-index** — as the project needs.

### 3. Component & pattern conventions
How components consume tokens; the standard variants and states (default, hover, active, disabled, loading, empty, error); the accessibility baseline (focus rings, contrast, target sizes, motion). Keep these consistent with `${CLAUDE_PLUGIN_ROOT}/references/frontend/react.md` accessibility guidance.

### 4. Enforce
This is the reference `frontend` builds against and `code-review` can check: flag hardcoded values, off-token colors, ad-hoc spacing, and contrast failures. New values proposed by `ui-exploration` are reconciled here — added as tokens, not scattered as literals.

### 5. Hand off
Document the system (the tokens and the conventions) in the project — its `@theme`/theme file plus a short `docs/design-system.md` if warranted (via `documentation`). Point `frontend` at it.

## What this skill does NOT do
- Hardcode design values into components — tokens only.
- Replace an existing design system unprompted.
- Build feature screens/UI (that's `frontend`, consuming this system).
- Over-build a component library beyond the project's real scale.
