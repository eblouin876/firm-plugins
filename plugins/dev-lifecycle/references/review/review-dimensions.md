<!--
library: code-review
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Review dimensions (correctness, best practices, DRY, performance)

Detailed criteria for the non-security dimensions. Apply to the changed code and its blast radius. Security has its own file (`security.md`).

## Correctness & regression — "does it break anything?"
The most important dimension: working code that ships beats elegant code that breaks.

- **Logic:** off-by-one errors, inverted conditions, wrong operators, incorrect boundary handling, mishandled `null`/`None`/`undefined`/empty states.
- **Broken contracts:** if a function signature, return type, or behavior changed, do all callers still work? Did a renamed/removed export break imports? Did a changed API response shape break the frontend consuming it?
- **State & concurrency:** shared mutable state, race conditions, missing `await`, unhandled promise rejections, ordering assumptions that don't hold.
- **Error paths:** are failures handled, or do they throw unhandled and crash/500? Are partial failures left in an inconsistent state (e.g. write A succeeds, write B fails, no rollback)?
- **Tests:** does the change break existing tests? Should it have added or updated tests? Is the changed logic actually covered, or only the happy path?
- **Data flow:** trace inputs through the change to outputs. Does every branch produce a valid result?

## Best practices & conventions
"Best practice" = idiomatic for this stack/version AND consistent with this codebase. Defer to the project; the `frontend` and `backend` skills define the substantive standards.

- **Version-correct idioms:** patterns valid for the installed React / Pydantic / SQLAlchemy version (see those skills). Flag legacy patterns where a modern one applies, and modern APIs used on a version that lacks them.
- **Consistency:** matches existing naming, file/folder structure, error-handling style, and patterns. A change that's "good" but alien to the codebase still adds friction.
- **Separation of concerns:** business logic out of route handlers and components; presentation separate from data access; single-responsibility units.
- **Readability:** clear names, reasonable function size, no dead code, no leftover debug prints/`console.log`, no commented-out blocks shipped.
- **Typing:** honest types, no `any`/`# type: ignore` as an escape hatch, no silenced linters hiding real issues.
- **Magic values & config:** constants named, configuration not hardcoded.

## DRY (Don't Repeat Yourself)
- Logic duplicated by this change — the same computation, validation, or transform written more than once where one source of truth would do.
- Copy-paste that drifts: near-identical blocks that will need to be fixed in multiple places.
- Reinvented wheels: hand-rolled logic that duplicates an existing project utility or a well-known library function.
- **Don't over-correct:** incidental similarity is not duplication. Two things that look alike today but change for different reasons should often stay separate. Premature abstraction is its own cost — flag genuine, meaningful repetition, not every echo.

## Performance & scalability
Focus on what degrades as data or traffic grows, not micro-optimizations.

- **N+1 queries:** a query inside a loop over rows; relationships lazy-loaded per item. The classic backend performance bug — flag it and suggest eager loading / a batched query.
- **Unbounded work:** list endpoints/queries with no pagination or limit; loading an entire table to compute something the DB could; rendering an unvirtualized huge list on the frontend.
- **Algorithmic complexity:** accidental O(n²) (nested loops over the same growing collection), repeated work that could be hoisted/memoized, expensive operations in hot paths.
- **Database:** new frequent query/filter/sort/join patterns without a supporting index; `SELECT *` pulling unused columns; missing query limits.
- **Async hygiene:** blocking I/O on an async path stalling the event loop; sequential awaits that could run concurrently; unnecessary round-trips.
- **Frontend:** avoidable re-renders, unmemoized expensive work where the React Compiler isn't handling it, large bundle additions, unbatched network requests.
- **Caveat:** don't demand optimization without cause. Note the cost and when it'll bite ("fine now; will be slow past ~10k rows"), and prioritize accordingly.
