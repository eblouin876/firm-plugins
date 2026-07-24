// Layers typescript-eslint on top of the workspace-root flat config, per the
// root eslint.config.mjs's own note that TS packages add their own
// parser/plugins rather than the base carrying them for everyone. Same shape
// as @repo/api-client, @repo/web-shared, and the Vite SPA block.
//
// Deliberately does NOT add `eslint-config-next` — that package pulls in its
// own React/JSX/hooks/a11y rule sets and a Next-specific plugin dependency
// this kit hasn't pinned on the compatibility matrix; the workspace-root
// config + typescript-eslint's recommended rules are the kit's baseline for
// every TS app, Next included.
//
// NOTE (materialized-location path): like tsconfig.json, this app is authored
// at templates/frontend/nextjs/ but lands at <project>/apps/web/ once
// scaffolded, so "../../eslint.config.mjs" below is written for that
// materialized location (two levels up to the project root), not for this
// file's position in eblouin-plugins.
import tseslint from "typescript-eslint";
import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  ...rootConfig,
  {
    // .next/ is Next's build output; nothing hand-written to lint there.
    ignores: [".next/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        // next.config.ts and postcss.config.mjs aren't under this app's
        // tsconfig `include` (that's `app`/`components`/`src` only), so
        // linting them needs an explicit opt-in to a default (non-project)
        // parser service — same pattern the Vite SPA uses for vite.config.ts,
        // and @repo/web-shared uses for its vitest.config.ts/vitest.setup.ts.
        projectService: {
          allowDefaultProject: ["next.config.ts", "vitest.config.ts", "vitest.setup.ts"],
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
