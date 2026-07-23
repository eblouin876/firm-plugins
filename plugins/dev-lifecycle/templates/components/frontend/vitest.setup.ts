// Extends vitest's `expect` with jest-dom's DOM matchers (toBeInTheDocument,
// toHaveTextContent, ...). Loaded once via vitest.config.ts's `setupFiles`.
// Testing Library's automatic cleanup is registered by its own module when it
// detects the global `afterEach` (config sets `globals: true`) — no manual
// cleanup wiring needed here.
import "@testing-library/jest-dom/vitest";
