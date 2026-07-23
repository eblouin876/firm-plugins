/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vitest config for the `admin` app — TEST-ONLY. Neither `next dev` nor
// `next build` ever reads this file; Next owns its own build pipeline
// (Turbopack, configured in next.config.ts). Vitest is itself built on Vite,
// so running `pnpm --filter admin test` still spins up a Vite instance purely
// to transform/serve files for the test run — @vitejs/plugin-react supplies
// the JSX transform (this app's tsconfig sets `jsx: "preserve"` for Next's
// own SWC/Turbopack compiler, which Vite's default esbuild transform does not
// know how to turn into runnable JS on its own) plus Fast Refresh, the same
// plugin the Vite SPA block and the `web` app wire in for a related but
// distinct reason (there, Vite builds the whole app; here, it only powers the
// test transform, alongside Next's separate, unrelated Turbopack pipeline).
//
// jsdom + a fixed origin + `document.cookie` support: same rationale as the
// Vite SPA's / `web` app's vitest.config.ts test block — jsdom gives
// `document`/`window` so React renders headlessly and the api-client
// mutator's cookie-mode CSRF echo (which reads `document.cookie`) works, and
// the fixed `http://localhost` origin lets MSW match absolute handler URLs.
// `css: false` skips CSS processing in tests (no test imports the Tailwind
// entry / app/globals.css).
//
// No `resolve.alias` for @repo/api-client / @repo/web-shared: pnpm
// workspaces already symlinks those packages into this app's own
// node_modules/@repo/* (their package.json `main`/`types` point at the
// already-built dist/), so plain node_modules resolution finds them with
// zero extra config — exactly how the Vite SPA's/`web` app's vite.config.ts
// resolve the same two packages (no aliases there either). Run `pnpm --filter
// @repo/api-client build && pnpm --filter @repo/web-shared build` (or a full
// `pnpm install` + workspace build) before `pnpm --filter admin test` if
// either package's dist/ is stale or missing.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost" } },
    globals: true,
    css: false,
    setupFiles: ["./vitest.setup.ts"],
  },
});
