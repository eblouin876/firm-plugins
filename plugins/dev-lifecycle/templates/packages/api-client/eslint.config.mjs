// Layers typescript-eslint on top of the workspace-root flat config, per
// eslint.config.mjs's own note that TS packages add their own parser/plugins
// rather than the base carrying them for everyone.
//
// NOTE (materialized-location path): like tsconfig.json, this package is
// authored at templates/packages/api-client/ but lands at
// <project>/packages/api-client/ once scaffolded, so "../../eslint.config.mjs"
// below is written for that materialized location (two levels up to the
// project root), not for this file's position in firm-plugins.
import tseslint from "typescript-eslint";
import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  ...rootConfig,
  {
    // Generated code — "Do not edit manually" per its own header. Lint the
    // hand-written source; don't hold codegen output to hand-written rules.
    ignores: ["src/generated/**", "dist/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        // orval.config.ts isn't under this package's tsconfig `include`
        // (it drives codegen for src/, it isn't part of the built package),
        // so it needs an explicit opt-in to typed linting via a default
        // (non-project) parser service instead of being excluded outright.
        projectService: {
          allowDefaultProject: ["orval.config.ts"],
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
