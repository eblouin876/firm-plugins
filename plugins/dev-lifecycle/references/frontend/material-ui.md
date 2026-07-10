<!--
library: material-ui
versions-covered: "6, 7"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://mui.com/material-ui/getting-started
  - https://mui.com/material-ui/migration/upgrade-to-v7
-->

# Material UI (MUI) conventions

Granular guidance for building UI with MUI. Read after detecting `@mui/material` in `package.json`. Subordinate to the project's existing theme and conventions. Pairs with `react.md` (component/hook discipline) and the `design-system` skill (which owns the theme tokens this styling should honor).

## Contents
- Version check (do this first)
- Theming
- Styling: sx vs styled vs the slot pattern
- Components & layout
- Forms & accessibility
- Performance

## Version check (do this first)
- **MUI v7** is the current major (note: v8 was skipped so the numbering aligns with MUI X v9). The decisive v6→v7 changes:
  - **Package layout uses the `exports` field** — multi-level deep imports no longer work. Import from the public entry: `import { createTheme } from '@mui/material/styles'`, not `@mui/material/styles/createTheme`. This fixes ESM/CJS issues with Vite/webpack but breaks previously-private deep imports.
  - **Removed long-deprecated APIs:** `createMuiTheme` → use `createTheme`; `experimentalStyled` → use `styled`; `Hidden`/`PigmentHidden` removed; `Dialog`'s `onBackdropClick` → handle via `onClose(event, reason)`.
  - **Slot pattern standardized** across components (customize internals via `slots`/`slotProps`).
  - **CSS layers** supported via `enableCssLayer` (`StyledEngineProvider`, or `AppRouterCacheProvider` for Next App Router) — useful for controlling specificity against Tailwind or other CSS.
  - Uses `react-is@19`; pair with React 19 (pin `react-is` to your React version to avoid prop-type runtime errors on mixed setups).
  - First-party **Tailwind v4 integration** improved — if the project mixes MUI and Tailwind, see `tailwind.md` and use CSS layers to keep specificity sane.
- **MUI v6**: older deep-import paths and the now-removed APIs still work. Match what's installed; don't write v7 idioms into a v6 project or vice versa. Note Joy UI was removed from the MUI Core repo — don't assume it's available.

If unsure whether an API exists in the installed major, check the versioned docs for that major rather than recalling.

## Theming
- Define one theme with `createTheme` and provide it at the root via `ThemeProvider`; include `CssBaseline` for the baseline reset.
- Put design decisions in the **theme**, not scattered inline: palette, typography, spacing, shape, and component defaults via `theme.components[...].defaultProps`/`styleOverrides`. This is where the `design-system` skill's tokens land — a component should read from the theme, not hardcode a hex or a pixel value.
- For dark mode / multi-theme, use the CSS-variables theme (`cssVariables: true`) so switching doesn't require a re-render of the whole tree.

## Styling: sx vs styled vs the slot pattern
- **`sx`** for one-off, component-local styling — concise and theme-aware (`sx={{ mt: 2, color: 'primary.main' }}`). It has a small runtime cost; fine for leaves, avoid it in hot, frequently-re-rendered lists.
- **`styled()`** for reusable styled components and anything applied repeatedly — it's more performant than `sx` at volume and gives a named, reusable unit.
- **Slots (`slots`/`slotProps`)** to customize a component's internal elements in v7's standardized pattern, instead of reaching for removed deep imports or brittle class-name overrides.
- Prefer theme tokens (`primary.main`, `spacing(2)`) over literal values so the design system stays the single source of truth.

## Components & layout
- Use MUI's layout primitives (`Box`, `Stack`, `Grid`) rather than hand-rolled fl/grid wrappers; `Stack` for 1-D spacing, `Grid` for 2-D layout.
- Reach for the component's documented props before overriding styles — most spacing/variant needs are expressible without custom CSS.
- Don't fight the component: if you're overriding heavily, check whether a different component or an unstyled Base UI primitive fits better.

## Forms & accessibility
- MUI inputs are accessible when used correctly: every field needs a label (`TextField` `label`, or `FormControl` + `InputLabel` + `FormHelperText`). Don't strip the label for a placeholder.
- Surface validation errors via `error` + `helperText`; tie them to the field so assistive tech announces them.
- Verify keyboard operability and focus for dialogs/menus/drawers — MUI handles focus trapping, but custom slot content can break it.
- Color is never the only signal (see `react.md` accessibility notes).

## Performance
- Favor `styled()` over `sx` for anything rendered many times; memoize the theme object (create it once, not per render).
- Don't import the whole library barrel where a specific import works; v7's `exports` field already discourages deep private imports, so use the public paths.
- For long lists, virtualize (MUI X Data Grid, or a virtualization lib) rather than rendering thousands of MUI rows.
