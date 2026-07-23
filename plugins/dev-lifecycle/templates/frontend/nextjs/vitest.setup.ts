// Extends vitest's `expect` with jest-dom's DOM matchers (toBeInTheDocument,
// toHaveTextContent, ...). Loaded once via vitest.config.ts's `test.setupFiles`.
// Testing Library's automatic cleanup registers itself off the global
// `afterEach` (config sets `globals: true`) — no manual cleanup wiring needed.
// Byte-for-byte the same setup file the Vite SPA block uses.
import "@testing-library/jest-dom/vitest";
