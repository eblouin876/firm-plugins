// Extends vitest's `expect` with jest-dom's DOM matchers (toBeInTheDocument,
// toHaveTextContent, ...). Loaded once via vite.config.ts's `test.setupFiles`.
// Testing Library's automatic cleanup registers itself off the global
// `afterEach` (config sets `globals: true`) — no manual cleanup wiring needed.
import "@testing-library/jest-dom/vitest";
