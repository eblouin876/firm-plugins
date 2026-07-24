// Layers typescript-eslint on top of the workspace-root flat config, per
// eslint.config.mjs's own note that TS packages add their own parser/plugins
// rather than the base carrying them for everyone. Same shape as
// @repo/api-client's eslint.config.mjs.
//
// NOTE (materialized-location path): like tsconfig.json, this package is
// authored at templates/components/frontend/ but lands at
// <project>/packages/web-shared/ once scaffolded, so "../../eslint.config.mjs"
// below is written for that materialized location (two levels up to the
// project root), not for this file's position in eblouin-plugins.
import tseslint from "typescript-eslint";
import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  ...rootConfig,
  {
    // dist/ is build output; nothing hand-written to lint there.
    ignores: ["dist/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        // The vitest config + setup files aren't under this package's
        // tsconfig `include` (that's `src` only), so typed linting needs an
        // explicit opt-in to a default (non-project) parser service for them
        // — same pattern api-client uses for orval.config.ts.
        projectService: {
          allowDefaultProject: ["vitest.config.ts", "vitest.setup.ts"],
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
