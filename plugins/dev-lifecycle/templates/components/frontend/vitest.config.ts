import { defineConfig } from "vitest/config";

// jsdom so React renders and the api-client mutator's cookie-mode CSRF echo
// (which reads `document.cookie`) works headlessly; `globals: true` so
// Testing Library's automatic `afterEach` cleanup registers and the setup
// file's jest-dom matchers attach to vitest's `expect`. A fixed jsdom URL
// gives requests a stable origin for MSW to match absolute handler URLs
// against.
export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost" } },
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
});
