---
name: frontend
description: Build, modify, or review frontend web UI following modern best practices. Use this skill WHENEVER the work involves the client-facing layer of a web app — React components, pages, hooks, state, forms, styling, or server-rendered HTML/templates with HTMX and Tailwind. Trigger it for "build the UI for X", "add a component", "wire up this page", "make this form work", "style this", or any frontend task that follows a plan. Before writing any frontend code, this skill ALWAYS detects the project's existing stack and the exact versions and conforms to what's already there rather than imposing a different framework.
---

# Frontend

Build frontend that fits the project as it actually is — not a generic template. The single biggest source of bad frontend work is assuming a stack and a version instead of checking. This skill front-loads that check, then writes code that matches the project's real conventions, framework, and version.

## Core rules

- **Detect before you build.** Never assume the framework, version, styling system, or conventions. Read the project first (step 1). Not optional.
- **Conform, don't convert.** If the project uses React, write React. If it uses server-rendered templates + HTMX, write that. Never introduce a new framework, state library, or styling system into an existing app without the user asking. Match existing patterns even when you'd personally choose differently.
- **Version dictates idiom.** React 18 and 19 are written differently; Tailwind v3 and v4 are configured differently; MUI v6 and v7 import differently. The "modern" way depends on the installed version — check it, then write for that version.
- **Work context-efficiently.** Detect from `package.json`/lockfile, not by reading the tree; read one or two representative components for house style; load only the reference(s) for the libraries actually present. See `${CLAUDE_PLUGIN_ROOT}/shared/token-efficiency.md`.
- **Implement against a plan when one exists.** Build to the plan; if there's no plan and the work is non-trivial, suggest planning first.

## Workflow

### 1. Detect the stack (always)
Read **`package.json`** and the **lockfile** for: React and its major (`react`/`react-dom`), the meta-framework (`next`, `react-router`, `astro`, `vite`), state libs, styling (`tailwindcss`, MUI, CSS modules), TypeScript, and the test runner. **No `package.json` + server-side templates** (Django/Jinja, `*.html` with `hx-*`) → server-rendered path. Read config files and one or two representative components to mirror house style.

State what you found in a line, e.g. "React 19 + Vite + TypeScript + MUI v7 + Tailwind v4 — following those."

### 2. Choose the approach (greenfield / open-ended only)
If a stack exists, step 1 already decided. Only when starting fresh: reach for **React (+ meta-framework)** for rich client state and app-like interactivity; reach for **server-rendered HTML + HTMX + Tailwind** when interactivity is mostly request/response (forms, partial swaps) and you want minimal JS. Don't over-engineer — a form-driven CRUD app doesn't need a SPA. State the choice and reason.

### 3. Build
Load only the references for what's actually present:
- **React** → `${CLAUDE_PLUGIN_ROOT}/references/frontend/react.md`; if TypeScript, `typescript.md`; if MUI, `material-ui.md`; if Tailwind, `tailwind.md`.
- **Server-rendered + HTMX** → `${CLAUDE_PLUGIN_ROOT}/references/frontend/htmx.md` (+ `tailwind.md` for styling). Pairs with the backend skill's Django path.
- If a significant UI library has **no reference yet**, generate one from current official docs, use it now, and PR it into the plugin (self-extend flow).

Both paths: match existing conventions; accessibility is not optional (semantic HTML, labels, keyboard operability, focus management, contrast, alt text); handle loading/empty/error states; keep components/templates small; if TypeScript is present, type honestly (no `any` escape hatch).

### 4. Hand off
Summarize what changed (files, components, routes) so it's reviewable. Note anything to verify (a visual result, a route needing a backend endpoint) and follow-ups left out of scope. The bar for merge-ready is `${CLAUDE_PLUGIN_ROOT}/shared/definition-of-done.md`.

## What this skill does NOT do
- Assume a framework or version without checking.
- Introduce a new framework, state library, or styling system into an existing project unprompted.
- Build the backend/API (that's the backend skill — this skill consumes APIs, it doesn't define them).
- Skip accessibility or error/loading states to "keep it simple."
