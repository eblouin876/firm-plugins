<!--
library: react
versions-covered: "18, 19"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://react.dev
  - https://react.dev/blog
-->

# React conventions

Granular guidance for writing React. Read this after detecting that the project uses React. Everything here is subordinate to the project's existing conventions — when they conflict, the project wins.

## Contents
- Version check (do this first)
- Component design
- Hooks discipline
- State management
- Data fetching
- Forms
- Performance
- Accessibility
- TypeScript
- Testing

## Version check (do this first)

The installed React major changes how idiomatic code is written. Confirm the version from `package.json` / lockfile, then write for that version. Don't use an API from a version the project isn't on, and don't write legacy patterns when a newer, simpler one is available in the installed version.

**React 19 (stable since late 2024) makes several older patterns obsolete:**
- Actions and the `useActionState` / `useFormStatus` hooks for form submission and pending state, instead of hand-rolled `useState` + `isSubmitting` flags.
- The `use` API for reading promises/context conditionally.
- `ref` as a regular prop — `forwardRef` is no longer needed for most components.
- Document metadata (`<title>`, `<meta>`, `<link>`) can be rendered directly in components.
- The React Compiler can auto-memoize, reducing the need for manual `useMemo`/`useCallback`/`memo`. If the compiler is enabled in the project (check the build/babel/eslint config), do not litter the code with manual memoization — let the compiler do it. If it's not enabled, memoize deliberately (see Performance).
- Server Components / Server Actions are stable; in an RSC-based framework (e.g. Next App Router), default to Server Components and opt into Client Components (`"use client"`) only where interactivity or browser APIs require it.

**React 18 projects:** no Actions, no `use`, `forwardRef` still required, manual memoization is the norm, no React Compiler. Write accordingly.

**Currency (2026-07):** React 19.x is the current stable line; React 20 has not shipped. If the project uses React Server Components, confirm it's on a release patched against the RSC deserialization RCE advisory (CVE-2025-55182, "React2Shell") — fixed in 19.0.1 / 19.1.2 / 19.2.1 and the corresponding Next.js 15.x/16.x lines.

If you're unsure whether an API exists or behaves a certain way in the installed version, check the current official docs and the version's release notes rather than guessing — these details shift between minor releases.

## Component design
- Function components only. No class components in new code.
- One component per concern. If a component renders, fetches, transforms, and handles a dozen events, split it.
- Co-locate: keep a component's styles, types, and small helpers near it.
- Props are the contract — keep them minimal and explicit. Prefer passing data over passing setters when feasible; lift state only as high as it needs to go.
- Composition over configuration: a pile of boolean props (`isPrimary`, `isLarge`, `isGhost`...) is a signal to split or use `children`/slots.

## Hooks discipline
- Effects are for synchronizing with external systems (subscriptions, DOM, network side-effects) — not for deriving state. If a value can be computed during render from props/state, compute it; don't mirror it into state via an effect.
- Every effect needs correct, exhaustive dependencies. Don't silence the lint rule to dodge a re-run bug — fix the underlying design.
- Clean up subscriptions, timers, and listeners in the effect's cleanup function.
- Extract reusable stateful logic into custom hooks (`useX`) with a clear single responsibility.

## State management
- Start local (`useState`/`useReducer`). Lift state up only when it must be shared.
- Reach for Context for genuinely cross-cutting, low-frequency state (theme, auth, locale) — not as a general-purpose store; high-frequency Context updates cause wide re-renders.
- Add a client state library (Zustand, Redux Toolkit, Jotai) only when the project already uses one or the complexity genuinely warrants it. Follow whatever the project already standardized on.
- Keep server state out of client state stores — use a data-fetching library for it (below).

## Data fetching
- If the project uses a server-data library (TanStack Query, SWR, RTK Query, or a framework's loaders), use it — don't hand-roll fetch-in-`useEffect` alongside it.
- In an RSC framework, fetch in Server Components / route loaders where possible; push fetching to the server rather than the client.
- Always handle the three states explicitly: loading, error, and empty. A component that only renders the success path is incomplete.
- Don't trigger waterfalls: fetch in parallel where the data is independent.

## Forms
- React 19: prefer Actions + `useActionState` for submission, validation feedback, and pending UI.
- React 18 or controlled-form needs: controlled inputs with a single source of truth, or a form library if the project uses one (React Hook Form, etc.) — match the project.
- Validate on the client for UX, but never trust the client; the backend validates for real.
- Tie every input to a `<label>`. Surface validation errors near the field and announce them to assistive tech.

## Performance
- Measure before optimizing. Don't sprinkle `useMemo`/`useCallback` preemptively — they have a cost and add noise.
- If the React Compiler is on, rely on it for memoization and keep code clean.
- If it's off, memoize deliberately: stabilize props passed to memoized children, memoize genuinely expensive computations, and `memo` components that re-render needlessly with the same props.
- Virtualize long lists. Code-split at route boundaries and lazy-load heavy, below-the-fold, or rarely-used components.
- Give lists stable, meaningful `key`s — never the array index when the list can reorder.

## Accessibility
- Semantic elements first (`button`, `nav`, `main`, `ul`); reach for ARIA only to fill gaps semantics can't.
- Interactive elements must be keyboard-operable and focusable, with visible focus.
- Manage focus on route changes, modal open/close, and dynamic content insertion.
- Label icon-only buttons. Ensure color is never the sole carrier of meaning, and meet contrast minimums.

## TypeScript
- If TS is present, type props, state, and function signatures honestly. No `any` as an escape hatch; prefer `unknown` + narrowing when a type is truly open.
- Type component props with an explicit interface/type. Avoid `React.FC` if the project doesn't already use it; type `children` as `React.ReactNode` when needed.
- Derive types from a single source of truth (e.g. infer from a schema/validator) rather than maintaining parallel definitions.

## Testing
- Use the project's runner (Vitest/Jest) and React Testing Library if present.
- Test behavior the user observes, not implementation details — query by role/label/text, not by class or component internals.
- Cover the unhappy paths (loading, error, empty, validation failure), not just the happy path.
