// Public surface of @repo/web-shared. Every export is framework-portable:
// no react-router, no `import.meta`, and no `document`/`window` access at
// module top level — so this package imports cleanly into a Vite SPA and a
// Next.js client component alike (the guards are render-gate primitives the
// app supplies router redirects to; see auth/guards).
//
// The barrel is filled as each leaf lands:
//   - Step 4 (errors / query / jwt primitives)
//   - Step 5 (auth provider + guards + form helpers)
export {};
