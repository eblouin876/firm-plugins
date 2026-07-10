<!--
library: htmx
versions-covered: "2.x"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://htmx.org/docs
-->

# Server-rendered + HTMX conventions

Granular guidance for the non-SPA path: HTML rendered by the server (Django templates, Jinja, FastAPI + a template engine), progressively enhanced with HTMX, styled with Tailwind. Read this after deciding on (or detecting) the server-rendered path. The project's existing conventions override anything here.

## Contents
- When this path fits
- Template structure
- HTMX usage
- Fragments / partial responses
- Progressive enhancement
- Forms & validation
- Tailwind
- Accessibility

## When this path fits
Server-driven apps where most interactivity is request/response: forms, filtering, pagination, inline edits, partial swaps. The server owns rendering and state; the client stays thin. If the UI needs rich, persistent client-side state or app-like interactions (drag-and-drop canvases, real-time collaborative editing, complex optimistic UI), that's a React signal — reconsider the path.

## Template structure
- One base layout with named blocks; pages extend it. Don't duplicate `<head>`, nav, and footer across templates.
- Factor repeated markup into includes/partials (`{% include %}`, macros). A partial that's also a valid standalone HTMX response is ideal (see Fragments).
- Keep logic out of templates. Compute in the view/handler; templates display. No business logic in the markup.
- Mirror the project's existing folder and naming conventions for templates and partials.

## HTMX usage
- Use `hx-get`/`hx-post`/`hx-put`/`hx-delete` to issue requests from any element; let the server return HTML, not JSON, for these.
- Control what updates with `hx-target` and `hx-swap`; default to the smallest swap that does the job (swap a fragment, not the whole page).
- Use `hx-trigger` deliberately — debounce search inputs (`keyup changed delay:300ms`), trigger on the right event, avoid accidental request storms.
- Reach for `hx-boost` to enhance ordinary links/forms into AJAX navigation without rewriting them.
- Show feedback during requests with `hx-indicator` and the `htmx-request` class. Don't leave the user wondering whether their click registered.
- Keep client JS minimal. If you need a sprinkle of behavior, a small script or Alpine/`_hyperscript` is fine when the project already uses it — don't pull in a framework.

## Fragments / partial responses
- A request that targets part of the page should return just that fragment, not a full document. Structure templates so the same partial renders both inside the full page and as a standalone HTMX response.
- A common pattern: detect the HTMX request server-side (e.g. the `HX-Request` header) and render the partial template instead of the full page.
- Return correct status codes and use response headers (`HX-Redirect`, `HX-Trigger`, `HX-Retarget`) to drive client behavior from the server when needed.

## Progressive enhancement
- Build it to work without JS first where feasible: real `<form>` actions and real links that hit working endpoints, then enhance with `hx-*`. This keeps the app resilient and accessible.
- Don't strand core functionality behind a swap that silently fails — degrade gracefully.

## Forms & validation
- Validate on the server; it's the source of truth. Re-render the form partial with errors inline on failure and swap it in.
- Tie inputs to labels, preserve user input on re-render, and place error messages adjacent to their fields.
- Use POST-redirect or `HX-Redirect` on success to avoid resubmission; or swap in a success fragment.

## Tailwind
> Full Tailwind conventions live in `tailwind.md` — load that reference for styling depth (v4 is CSS-first). The HTMX-specific point below is the one that matters here.
- Use utility classes in the markup; avoid premature extraction. When a pattern genuinely repeats, extract a component partial (preferred) or use the project's chosen abstraction.
- Follow the project's `tailwind.config` — its color tokens, spacing scale, and any design tokens. Don't hardcode arbitrary values when a token exists.
- Keep class lists readable; group by concern (layout, spacing, color, state) consistent with the codebase.
- Ensure Tailwind's content paths include your template/partial directories so classes aren't purged.

## Accessibility
- Semantic HTML is the baseline and you get a lot of it for free server-side — use real `button`, `a`, `label`, `nav`, `main`.
- After an HTMX swap, manage focus so keyboard and screen-reader users aren't lost — move focus to the new content or a sensible anchor.
- Use `aria-live` regions for content that updates in place (validation errors, async results) so changes are announced.
- Ensure swapped-in interactive content is keyboard-operable and that focus order stays logical.
