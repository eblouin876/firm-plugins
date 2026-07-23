// Layers typescript-eslint on top of the workspace-root flat config, per the
// root eslint.config.mjs's own note that TS packages add their own
// parser/plugins rather than the base carrying them for everyone. Same shape
// as @repo/api-client and @repo/web-shared.
//
// NOTE (materialized-location path): like tsconfig.json, this app is authored
// at templates/frontend/vite-spa/ but lands at <project>/apps/web/ once
// scaffolded, so "../../eslint.config.mjs" below is written for that
// materialized location (two levels up to the project root), not for this
// file's position in firm-plugins.
import tseslint from "typescript-eslint";
import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  ...rootConfig,
  {
    // dist/ is Vite build output; nothing hand-written to lint there.
    ignores: ["dist/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        // vite.config.ts and vitest.setup.ts aren't under this app's tsconfig
        // `include` (that's `src` only), so linting them needs an explicit
        // opt-in to a default (non-project) parser service — same pattern
        // @repo/web-shared uses for its vitest config.
        projectService: {
          allowDefaultProject: ["vite.config.ts", "vitest.setup.ts"],
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
