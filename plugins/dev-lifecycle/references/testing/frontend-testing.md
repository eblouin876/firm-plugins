<!--
library: testing-library, playwright
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Frontend testing conventions

Guidance for component tests (React Testing Library + the project's runner) and end-to-end tests (Playwright). Read after detecting a frontend. The project's existing conventions override anything here.

## Contents
- Component tests: principles
- Querying & interaction
- Network & module mocking
- What to test (and what not to)
- End-to-end (Playwright)
- Server-rendered / HTMX apps

## Component tests: principles
- Use the project's runner (`vitest`/`jest`) with `@testing-library/react`. Co-locate tests (`Component.test.tsx`) or follow the project's layout.
- **Test from the user's perspective.** Render the component, interact the way a user would, assert on what they'd observe. Don't reach into state, props, or instance internals.
- Tests should survive refactors: changing *how* a component is built (hooks, structure) shouldn't break a test if the *behavior* is unchanged. If a refactor breaks many tests, they were testing the wrong thing.

## Querying & interaction
- Query by accessible role, label, and text (`getByRole`, `getByLabelText`, `getByText`) — the way users and assistive tech find things. Avoid `getByTestId` except as a last resort, and never query by CSS class or DOM path.
- Drive interactions with `@testing-library/user-event` (realistic events) rather than firing raw synthetic events.
- For async UI, use `findBy*` / `waitFor` to await results instead of arbitrary timeouts.
- Bonus: role-based queries double as a light accessibility check — if you can't query by role, neither can a screen reader.

## Network & module mocking
- Mock the network at the boundary with **MSW (Mock Service Worker)** — intercept requests and return controlled responses, rather than stubbing your fetch/client functions. This tests the component's real data-fetching path.
- Mock time and randomness when behavior depends on them.
- Avoid over-mocking: if you mock everything the component touches, the test asserts nothing real.

## What to test (and what not to)
- **Do test:** conditional rendering, user interactions and their effects, form validation and submission, loading/error/empty states, and that the component calls the right boundary with the right data.
- **Don't test:** third-party libraries, styling/exact markup, or trivial pass-through components with no logic. Don't snapshot-test large trees as a substitute for real assertions — snapshots rot into rubber-stamped diffs.

## End-to-end (Playwright)
- Reserve e2e for a few critical user journeys (sign in → core task → result), not broad coverage — they're slow and the most brittle layer.
- Use Playwright's auto-waiting and role/text locators; avoid fixed sleeps.
- Run against a real built app with a known-seeded backend state; keep each spec independent and able to set up/tear down its own data.
- Stabilize: control the clock and external services, use unique test data per run, and make selectors robust (roles/labels over brittle CSS).

## Server-rendered / HTMX apps
- If the frontend is server-rendered (Django/Jinja + HTMX), most "frontend" behavior is exercised by backend view/partial tests (see backend-testing.md) — assert the right fragment and status come back.
- Use Playwright for the genuinely interactive flows (an `hx-*` swap updating the page, a form round-trip) to confirm the enhancement works end-to-end in a browser.
