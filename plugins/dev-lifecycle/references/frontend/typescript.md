<!--
library: typescript
versions-covered: "5.9, 6.0, 7.0"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://www.typescriptlang.org/docs
  - https://devblogs.microsoft.com/typescript
-->

# TypeScript conventions

Granular guidance for writing TypeScript. Read after detecting TS (`tsconfig.json`, `.ts`/`.tsx`). Subordinate to the project's existing config and conventions — when they conflict, the project wins. This is the default frontend language for the firm, and it also types shared API contracts, so honest types here pay off across the stack.

## Contents
- Version check (do this first)
- Strictness & compiler config
- Typing discipline
- Types from a single source of truth
- Modules & imports
- Errors & narrowing
- Tooling

## Version check (do this first)
The TypeScript line moved fast in 2026 — confirm the installed version and write for it.

- **TypeScript 7.0** (Go-based compiler, the "native" rewrite; first stable shipped mid-2026) is roughly 8–12× faster than 6.0 and is **semantically identical** to 6.0 — the type-checker was ported, not redesigned, so type-checking behavior is the same. It runs as `tsc`/`tsgo`. Two practical caveats: the **stable programmatic compiler API lands in 7.1, not 7.0**, so tools that depend on it (typescript-eslint, ts-morph, custom transformers) may need TypeScript 6.0 aliased alongside until 7.1; and 7.0 hard-adopts 6.0's stricter defaults, so a project that skipped 6.0 must audit `tsconfig` before upgrading.
- **TypeScript 6.0** (last JS-based compiler) flipped several defaults **on**: `strict`, ESM modules, and an `es2025` target, and removed a batch of legacy options. If a project relies on loose defaults or ships CommonJS, those must now be set **explicitly** in `tsconfig.json`.
- **TypeScript 5.9 and earlier** use the old loose defaults — strict is opt-in. Match what's configured.

If unsure whether an API/flag exists in the installed version, check the current docs/release notes rather than recalling — this line is shifting.

## Strictness & compiler config
- `strict: true` is the target (and the default from 6.0). If the project is pre-6.0 and not strict, don't silently flip it — flag it as a follow-up; turning it on mid-project surfaces real errors that need real fixes.
- Keep `tsconfig` explicit about `module`, `target`, and `moduleResolution` rather than relying on version-dependent defaults, so an upgrade doesn't silently change emit.
- Type-checking in CI is a gate (`tsc --noEmit`, or `tsgo` on 7.0). Type errors fail the build (see the devops CI conventions).

## Typing discipline
- Type function signatures, exported values, and public boundaries honestly. Let inference handle obvious locals; annotate where it clarifies intent or crosses a boundary.
- **No `any` as an escape hatch.** Prefer `unknown` + narrowing when a type is genuinely open. `# type: ignore`'s TS equivalent — `@ts-ignore`/`@ts-expect-error` — is for documented, unavoidable cases, not to silence a real error. Prefer `@ts-expect-error` (it fails if the error disappears) over `@ts-ignore`.
- Prefer `type` aliases and `interface` per the project's existing convention; don't mix styles arbitrarily. Use discriminated unions for modeled states (loading/success/error) rather than boolean soup.
- Make illegal states unrepresentable where it's cheap: a union of valid shapes beats a wide object with optional everything.

## Types from a single source of truth
- Derive types rather than maintaining parallel definitions. Infer from a schema/validator (e.g. Zod, Valibot) with `z.infer<...>`, or generate client types from the backend's OpenAPI so the frontend's request/response types **are** the API contract (see the backend skill's OpenAPI output and the codegen the frontend skill wires up).
- One canonical definition, imported everywhere — not a hand-copied interface that drifts from the API.

## Modules & imports
- ESM is the modern default (and 6.0+'s default). Use `import`/`export`; avoid CommonJS interop unless the project requires it.
- Use `import type { … }` for type-only imports so bundlers can erase them cleanly (and 7.0's stricter emit is happy).
- Respect path aliases from `tsconfig` `paths`; don't hand-roll deep relative chains when an alias exists.

## Errors & narrowing
- Narrow with type guards, `in`, `instanceof`, and discriminant checks rather than casting. A cast (`as`) asserts you know better than the compiler — reserve it for genuine boundaries (parsed external data you've validated), not to paper over a mismatch.
- Catch clauses are `unknown` in strict mode — narrow before use; don't assume `error.message` exists.

## Tooling
- Lint with the project's setup (typescript-eslint / Biome). If on 7.0 and a tool needs the stable API, alias TypeScript 6.0 for that tool until 7.1.
- Keep types and the code that uses them together; co-locate a component's props type with the component.
