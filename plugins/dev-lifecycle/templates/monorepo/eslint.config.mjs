// Flat ESLint config (ESLint 9+ / flat config format) shared across the
// monorepo workspace. Individual packages/apps may layer stack-specific
// config (e.g. React, Next.js) on top of this base — see the block that
// scaffolded them for its own eslint.config.mjs, if any.
//
// Kept dependency-light at Stage 1: no plugins are required for the empty
// skeleton to lint clean. Stack-specific blocks (Stage 2+) add their own
// parser/plugins as they're scaffolded in.

export default [
  {
    ignores: ["**/dist/**", "**/build/**", "**/node_modules/**", "**/.turbo/**", "**/coverage/**"],
  },
  {
    // JS-only at the base: espree cannot parse TypeScript, so .ts/.tsx files
    // are covered per-package by typescript-eslint (each TS package layers
    // its own parser via `languageOptions.parser`) rather than here.
    files: ["**/*.{js,mjs,cjs,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "off",
    },
  },
];
