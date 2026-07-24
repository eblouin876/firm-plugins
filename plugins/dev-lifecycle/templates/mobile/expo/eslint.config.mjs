// Layers typescript-eslint on top of the workspace-root flat config, matching
// how packages/api-client does it (the base is JS-only; TS packages add their
// own parser/plugins). Written for the MATERIALIZED location apps/mobile/ —
// "../../eslint.config.mjs" is two levels up to the project root, not this
// file's position inside eblouin-plugins. Kept dependency-light: no RN-specific
// plugin, matching the kit's lean base config.
import tseslint from "typescript-eslint";
import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  ...rootConfig,
  {
    // Expo/Metro build + codegen output — not hand-written source.
    ignores: ["dist/**", ".expo/**", "expo-env.d.ts", "babel.config.js", "metro.config.js"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
