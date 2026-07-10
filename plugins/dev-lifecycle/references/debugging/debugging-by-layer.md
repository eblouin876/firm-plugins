<!--
library: debugging
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Debugging by layer

Where common bugs hide in each layer, and what to check. Use after the methodology has localized the failure to a layer. Pair with the frontend/backend skills for the fix.

## Contents
- Backend (FastAPI / Django / Python)
- Database (SQLAlchemy / Postgres)
- Async / concurrency
- Frontend (React)
- The integration boundary (frontend ⇄ backend)
- Performance problems

## Backend (FastAPI / Django / Python)
- **500s:** read the server-side traceback (the client message is sanitized). The real cause is in the logs.
- **422 / validation:** the request doesn't match the schema — compare the actual payload against the Pydantic model field by field.
- **401/403:** distinguish authentication (who) from authorization (allowed) — check which one is failing and where the dependency enforces it.
- **Wrong values:** check mutable default arguments, shared module-level state, and incorrect type coercion. Confirm config/env is what you think (print the resolved value).
- **Import/startup errors:** circular imports, wrong working directory, missing env var at boot.

## Database (SQLAlchemy / Postgres)
- **Stale / missing data:** is the transaction committed? Are you reading on a different session/transaction than the write? Autoflush/expire behavior surprising you?
- **`IntegrityError`:** a constraint fired — unique, FK, not-null. The DB is telling you the real rule; read which constraint.
- **It works in a test but not live (or vice versa):** different data, different isolation, or SQLite-in-tests masking a Postgres-specific behavior.
- **Migration issues:** schema out of sync with models — check the applied migration state vs the model definitions.
- **Mysterious slowness:** see Performance; suspect N+1 first.

## Async / concurrency
- **`RuntimeError` / event-loop errors:** sync blocking call on an async path, or mixing sync and async sessions/clients.
- **Hangs / deadlocks:** an `await` that never resolves, an unawaited coroutine, or lock ordering.
- **Race conditions:** order-dependent results, lost updates — reproduce by forcing the interleaving; look for shared state mutated without synchronization.
- A missing `await` is a classic: the coroutine is created but never run, so the "result" is a coroutine object or the effect never happens.

## Frontend (React)
- **Stale state / wrong value rendered:** a closure capturing an old value, a missing/incorrect effect dependency, or state derived in an effect instead of during render.
- **Infinite re-render / loop:** setting state unconditionally in render or in an effect whose deps change every render (new object/array identity each time).
- **Effect runs too often / not enough:** wrong dependency array. Read what's actually in deps vs what the effect reads.
- **"Not updating":** mutating state in place instead of creating a new reference; or a key reuse issue in a list.
- **Nothing renders / blank:** check the console for a thrown error and the network tab for a failed fetch; an error in render can blank the tree.
- Use React DevTools to inspect props/state/renders rather than guessing.

## The integration boundary (frontend ⇄ backend)
The classic "frontend blames backend, backend blames frontend." Get evidence from the wire:
- Open the **network tab**: inspect the actual request (URL, method, headers, body) and the actual response (status, body). The truth is on the wire, not in either side's assumptions.
- **CORS errors:** a backend configuration issue (missing/incorrect allowed origins/headers), not a frontend bug — read the exact CORS message.
- **Shape mismatch:** the response doesn't match what the client expects — compare against the API contract (the one the backend skill defined and the documentation skill recorded). One of the three has drifted.
- **Auth:** is the token actually attached and valid on the request that failed? Check the header on the wire.
- **404 to an endpoint that exists:** trailing-slash, path prefix/version, or method mismatch.

## Performance problems
- **Measure, don't guess.** Profile / time the slow path; find the actual hotspot before optimizing. The bottleneck is often not where intuition says.
- **Backend:** N+1 queries are the first suspect (query in a loop / lazy-loaded relationship per row); then missing indexes on new query patterns, unbounded result sets, and blocking I/O on async paths. Use `EXPLAIN ANALYZE` for slow queries.
- **Frontend:** avoidable re-renders, large/unsplit bundles, unvirtualized long lists, and request waterfalls. Use the profiler.
- Confirm the fix with the same measurement that found the problem — don't assume it helped.
