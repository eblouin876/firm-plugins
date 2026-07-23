// Next's first-party Tailwind v4 integration is the PostCSS plugin, NOT the
// `@tailwindcss/vite` plugin the Vite SPA uses (Next doesn't expose a Vite
// plugin pipeline) — see references/compatibility-matrix.md's "Frontend/web"
// row for the version this is pinned to (kept in lockstep with `tailwindcss`
// core).
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
